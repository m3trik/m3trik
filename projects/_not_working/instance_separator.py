# !/usr/bin/python
# coding=utf-8
"""Utilities for splitting meshes into instantiable groups.

The :class:`InstanceSeparator` encapsulates the discovery logic that powers the
auto-instancing workflow. It analyzes the supplied transforms, captures the
geometry payload for each mesh, and groups payloads that satisfy the similarity
criteria so downstream tools can decide how to handle them (convert to real
instances, export, report diff-only payloads, etc.).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pymel.core as pm
from maya.api import OpenMaya as om
import pythontk as ptk

from mayatk.mat_utils import MatUtils
from mayatk.node_utils import NodeUtils
from mayatk.xform_utils import XformUtils
from mayatk.xform_utils.matrices import Matrices


@dataclass
class InstancePayload:
    """Captured information for a single transform slated for instancing."""

    transform: pm.nodetypes.Transform
    shape: pm.nodetypes.Mesh
    matrix: om.MMatrix
    bbox_center: Tuple[float, float, float]
    bbox_size: Tuple[float, float, float]
    materials: Tuple[str, ...]
    parent: Optional[pm.nodetypes.Transform]
    visibility: bool
    vertex_count: int
    source_transform: pm.nodetypes.Transform
    local_matrix: om.MMatrix
    world_position: Tuple[float, float, float]

    @property
    def material_signature(self) -> Tuple[str, ...]:
        return self.materials


@dataclass
class InstanceGroup:
    """Represents a prototype mesh and the payloads that can instance it."""

    prototype: InstancePayload
    members: List[InstancePayload] = field(default_factory=list)

    def add_member(self, payload: InstancePayload) -> None:
        self.members.append(payload)

    @property
    def all_payloads(self) -> List[InstancePayload]:
        return [self.prototype] + list(self.members)


@dataclass
class InstanceSeparationResult:
    """Lightweight container for the grouping outcome."""

    groups: List[InstanceGroup]
    payload_count: int
    assemblies: List["AssemblyDescriptor"]
    assembly_groups: List["AssemblyGroup"]

    @property
    def instantiable_groups(self) -> List[InstanceGroup]:
        """Groups that contain at least one duplicate (prototype + members)."""

        return [group for group in self.groups if group.members]

    @property
    def unique_groups(self) -> List[InstanceGroup]:
        """Groups that did not find any duplicates."""

        return [group for group in self.groups if not group.members]

    @property
    def instantiable_payloads(self) -> List[InstancePayload]:
        payloads: List[InstancePayload] = []
        for group in self.instantiable_groups:
            payloads.extend(group.all_payloads)
        return payloads

    @property
    def unique_payloads(self) -> List[InstancePayload]:
        return [group.prototype for group in self.unique_groups]

    @property
    def instantiable_assembly_groups(self) -> List["AssemblyGroup"]:
        return [group for group in self.assembly_groups if group.members]

    @property
    def unique_assemblies(self) -> List["AssemblyDescriptor"]:
        return [group.prototype for group in self.assembly_groups if not group.members]


@dataclass
class AssemblyDescriptor:
    """Represents an original transform and its component payloads."""

    source_transform: pm.nodetypes.Transform
    components: List[InstancePayload]
    signature: Tuple[Tuple, ...]
    root_component: InstancePayload
    root_signature: Tuple
    matched_slots: Dict[int, InstancePayload] = field(default_factory=dict)


@dataclass
class AssemblyTemplateSlot:
    """Single component position inside an assembly template."""

    slot_id: int
    signature: Tuple
    reference_matrix: om.MMatrix
    prototype_payload: InstancePayload
    is_root: bool = False


@dataclass
class AssemblyGroup:
    """Groups assemblies that share identical component signatures."""

    prototype: AssemblyDescriptor
    template_slots: List[AssemblyTemplateSlot] = field(default_factory=list)
    members: List[AssemblyDescriptor] = field(default_factory=list)

    def add_member(self, descriptor: AssemblyDescriptor) -> None:
        self.members.append(descriptor)


class InstanceSeparator(ptk.LoggingMixin):
    """Encapsulates mesh comparison and grouping logic."""

    def __init__(
        self,
        tolerance: float = 0.98,
        require_same_material: bool = True,
        split_shells: bool = True,
        rebuild_instances: bool = True,
        template_position_tolerance: float = 0.1,
        template_rotation_tolerance: float = 5.0,
        derive_anchor_assemblies: bool = True,
        anchor_capture_multiplier: float = 4.0,
        collapse_rebuilt_assemblies: bool = True,
        verbose: bool = False,
    ) -> None:
        super().__init__()
        self.tolerance = tolerance
        self.require_same_material = require_same_material
        self.split_shells = split_shells
        self.rebuild_instances = rebuild_instances
        self.template_position_tolerance = template_position_tolerance
        self.template_rotation_tolerance = template_rotation_tolerance
        self.derive_anchor_assemblies = derive_anchor_assemblies
        self.anchor_capture_multiplier = anchor_capture_multiplier
        self.collapse_rebuilt_assemblies = collapse_rebuilt_assemblies
        self.verbose = verbose
        self._component_to_source: Dict[
            pm.nodetypes.Transform, pm.nodetypes.Transform
        ] = {}
        self._source_world_mats: Dict[pm.nodetypes.Transform, om.MMatrix] = {}

    # --------------------------------------------------------------------------
    # Public API
    # --------------------------------------------------------------------------
    def separate(
        self, nodes: Optional[Sequence[pm.nodetypes.Transform]] = None
    ) -> InstanceSeparationResult:
        """Analyze nodes and return grouping information without modifying them."""

        transforms = self._normalize_nodes(nodes)
        if not transforms:
            raise RuntimeError("No transforms supplied for instance separation.")

        self._component_to_source = {}
        self._source_world_mats = {}
        for transform in transforms:
            self._register_source_transform(transform)

        if self.split_shells:
            transforms = self._expand_shells(transforms)

        payloads = [self._build_payload(node) for node in transforms]
        payloads = [payload for payload in payloads if payload is not None]
        if not payloads:
            raise RuntimeError(
                "No mesh payloads discovered; aborting instance separation."
            )

        groups = self._group_payloads(payloads)
        assemblies = self._build_assemblies(payloads)
        assembly_groups = self._group_assemblies(assemblies)

        result = InstanceSeparationResult(
            groups=groups,
            payload_count=len(payloads),
            assemblies=assemblies,
            assembly_groups=assembly_groups,
        )

        if self.verbose:
            self._log_summary(result)

        if self.rebuild_instances:
            self._rebuild_instantiable_assemblies(result)

        return result

    # --------------------------------------------------------------------------
    # Internal helpers
    # --------------------------------------------------------------------------
    def _normalize_nodes(
        self, nodes: Optional[Sequence[pm.nodetypes.Transform]]
    ) -> List[pm.nodetypes.Transform]:
        if nodes:
            return pm.ls(nodes, transforms=True, flatten=True)
        return pm.ls(sl=True, transforms=True, flatten=True)

    def _expand_shells(
        self, transforms: Sequence[pm.nodetypes.Transform]
    ) -> List[pm.nodetypes.Transform]:
        expanded: List[pm.nodetypes.Transform] = []
        for transform in transforms:
            self._register_source_transform(transform)
            if not self._needs_shell_split(transform):
                expanded.append(transform)
                continue
            split_nodes = self._split_transform_shells(transform)
            if split_nodes:
                expanded.extend(split_nodes)
            else:
                expanded.append(transform)
        return expanded

    def _register_source_transform(self, transform: pm.nodetypes.Transform) -> None:
        if transform not in self._source_world_mats:
            try:
                self._source_world_mats[transform] = Matrices.to_mmatrix(transform)
            except RuntimeError:
                self._source_world_mats[transform] = om.MMatrix()
        if transform not in self._component_to_source:
            self._component_to_source[transform] = transform

    def _needs_shell_split(self, transform: pm.nodetypes.Transform) -> bool:
        shape = NodeUtils.get_shape_node(transform, returned_type="obj")
        if isinstance(shape, list):
            shape = shape[0] if shape else None
        if not shape or pm.nodeType(shape) != "mesh":
            return False
        try:
            shell_count = pm.polyEvaluate(shape, shell=True)
        except RuntimeError:
            return False
        if isinstance(shell_count, (list, tuple)):
            total = 0
            for value in shell_count:
                try:
                    total += int(value or 0)
                except (TypeError, ValueError):
                    continue
            shell_count = total
        if isinstance(shell_count, str):
            return False
        return int(shell_count or 0) > 1

    def _split_transform_shells(
        self, transform: pm.nodetypes.Transform
    ) -> List[pm.nodetypes.Transform]:
        parent = transform.getParent()
        visibility = bool(transform.visibility.get())

        pm.undoInfo(openChunk=True)
        separated_nodes = []
        try:
            separated_nodes = pm.polySeparate(transform, ch=False) or []
        finally:
            pm.undoInfo(closeChunk=True)

        valid_transforms: List[pm.nodetypes.Transform] = []
        for node in separated_nodes:
            if not node:
                continue
            try:
                py_node = pm.PyNode(node)
            except pm.MayaNodeError:
                continue
            if not isinstance(py_node, pm.nodetypes.Transform):
                continue

            shape = NodeUtils.get_shape_node(py_node, returned_type="obj")
            if isinstance(shape, list):
                shape = shape[0] if shape else None
            if not shape or pm.nodeType(shape) != "mesh":
                continue

            if parent:
                try:
                    pm.parent(py_node, parent, absolute=True)
                except RuntimeError:
                    pass

            py_node.visibility.set(visibility)
            self._component_to_source[py_node] = transform
            valid_transforms.append(py_node)

        return valid_transforms

    def _build_payload(self, transform) -> Optional[InstancePayload]:
        shape = NodeUtils.get_shape_node(transform, returned_type="obj")
        if isinstance(shape, list):
            shape = shape[0] if shape else None
        if not shape or pm.nodeType(shape) != "mesh":
            return None
        matrix = Matrices.to_mmatrix(transform)
        translation, _, _ = Matrices.decompose(matrix)
        source_transform = self._component_to_source.get(transform, transform)
        source_matrix = self._source_world_mats.get(source_transform)
        if source_matrix is None:
            try:
                source_matrix = Matrices.to_mmatrix(source_transform)
            except RuntimeError:
                source_matrix = om.MMatrix()
            self._source_world_mats[source_transform] = source_matrix
        local_matrix = Matrices.mult(Matrices.inverse(source_matrix), matrix)
        center, size = XformUtils.get_bounding_box(transform, "center|size")
        materials = tuple(sorted(MatUtils.get_mats(transform)))
        parent = transform.getParent()
        visibility = bool(transform.visibility.get())
        vertex_count = int(pm.polyEvaluate(shape, vertex=True))
        return InstancePayload(
            transform=transform,
            shape=shape,
            matrix=matrix,
            bbox_center=center,
            bbox_size=size,
            materials=materials,
            parent=parent,
            visibility=visibility,
            vertex_count=vertex_count,
            source_transform=source_transform,
            local_matrix=local_matrix,
            world_position=tuple(round(value, 4) for value in translation),
        )

    def _group_payloads(
        self, payloads: Iterable[InstancePayload]
    ) -> List[InstanceGroup]:
        groups: List[InstanceGroup] = []
        for payload in payloads:
            group = self._match_group(payload, groups)
            if group is None:
                groups.append(InstanceGroup(prototype=payload))
            else:
                group.add_member(payload)
        return groups

    def _build_assemblies(
        self, payloads: Iterable[InstancePayload]
    ) -> List[AssemblyDescriptor]:
        buckets: Dict[pm.nodetypes.Transform, List[InstancePayload]] = defaultdict(list)
        for payload in payloads:
            buckets[payload.source_transform].append(payload)

        assemblies: List[AssemblyDescriptor] = []
        for source, components in buckets.items():
            anchor_assemblies: List[AssemblyDescriptor] = []
            if self.derive_anchor_assemblies:
                anchor_assemblies = self._derive_anchor_assemblies(source, components)
            if anchor_assemblies:
                assemblies.extend(anchor_assemblies)
                continue
            signature = tuple(
                sorted(
                    self._assembly_component_signature(payload)
                    for payload in components
                )
            )
            root_component = max(components, key=self._payload_volume)
            root_signature = self._component_signature(root_component)
            assemblies.append(
                AssemblyDescriptor(
                    source_transform=source,
                    components=components,
                    signature=signature,
                    root_component=root_component,
                    root_signature=root_signature,
                )
            )
        return assemblies

    def _derive_anchor_assemblies(
        self,
        source_transform: pm.nodetypes.Transform,
        components: Sequence[InstancePayload],
    ) -> List[AssemblyDescriptor]:
        components = list(components)
        if len(components) < 2:
            return []

        anchors = self._select_anchor_payloads(components)
        if len(anchors) < 2:
            return []
        assembly_count = len(anchors)

        for template_anchor in anchors:
            descriptors = self._derive_from_template_anchor(
                template_anchor=template_anchor,
                anchors=anchors,
                components=components,
                source_transform=source_transform,
                assembly_count=assembly_count,
            )
            if descriptors:
                return descriptors

        return []

    def _derive_from_template_anchor(
        self,
        template_anchor: InstancePayload,
        anchors: Sequence[InstancePayload],
        components: Sequence[InstancePayload],
        source_transform: pm.nodetypes.Transform,
        assembly_count: int,
    ) -> List[AssemblyDescriptor]:
        template_slots = self._build_anchor_template_slots(
            template_anchor, components, assembly_count
        )
        if len(template_slots) <= 1:
            return []

        root_signature = self._component_signature(template_anchor)
        root_slots = [
            slot for slot in template_slots if slot.signature == root_signature
        ]
        if len(root_slots) != 1 or not root_slots[0].is_root:
            return []

        template_mapping = {
            slot.slot_id: slot.prototype_payload for slot in template_slots
        }
        descriptors: List[AssemblyDescriptor] = []
        used_transforms: set[pm.nodetypes.Transform] = set(
            payload.transform for payload in template_mapping.values()
        )

        template_descriptor = self._descriptor_from_slot_mapping(
            anchor=template_anchor,
            source_transform=template_anchor.transform,
            slot_payloads=template_mapping,
            template_slots=template_slots,
        )
        descriptors.append(template_descriptor)

        availability = self._build_anchor_availability(
            components=components,
            consumed_payloads=template_mapping.values(),
            anchors=anchors,
        )

        for anchor in anchors:
            if anchor is template_anchor:
                continue
            matches = self._match_anchor_to_template_slots(
                anchor, template_slots, availability
            )
            if not matches:
                continue
            descriptor = self._descriptor_from_slot_mapping(
                anchor=anchor,
                source_transform=anchor.transform,
                slot_payloads=matches,
                template_slots=template_slots,
            )
            descriptors.append(descriptor)
            used_transforms.update(
                payload.transform for payload in matches.values() if payload
            )

        if len(descriptors) <= 1:
            return []

        unused_components = [
            payload
            for payload in components
            if payload.transform not in used_transforms
        ]
        if unused_components:
            fallback = self._descriptor_from_components(
                source_transform=source_transform, components=unused_components
            )
            descriptors.append(fallback)

        return descriptors

    def _select_anchor_payloads(
        self, components: Sequence[InstancePayload]
    ) -> List[InstancePayload]:
        sorted_components = sorted(components, key=self._payload_volume, reverse=True)
        for candidate in sorted_components:
            signature = self._component_signature(candidate)
            duplicates = [
                payload
                for payload in components
                if self._component_signature(payload) == signature
            ]
            if len(duplicates) >= 2:
                return sorted(duplicates, key=lambda payload: payload.world_position)
        return []

    def _build_anchor_template_slots(
        self,
        anchor: InstancePayload,
        components: Sequence[InstancePayload],
        assembly_count: int,
    ) -> List[AssemblyTemplateSlot]:
        capture_radius = self._anchor_capture_radius(anchor, components, assembly_count)
        slots: List[AssemblyTemplateSlot] = []
        slot_id = 0
        for payload in components:
            if self._payload_distance(anchor, payload) > capture_radius:
                continue
            relative = self._relative_matrix(anchor.matrix, payload.matrix)
            slots.append(
                AssemblyTemplateSlot(
                    slot_id=slot_id,
                    signature=self._component_signature(payload),
                    reference_matrix=relative,
                    prototype_payload=payload,
                    is_root=payload is anchor,
                )
            )
            slot_id += 1
        return slots

    def _build_anchor_availability(
        self,
        components: Sequence[InstancePayload],
        consumed_payloads: Iterable[InstancePayload],
        anchors: Sequence[InstancePayload],
    ) -> Dict[Tuple, List[InstancePayload]]:
        consumed = {payload.transform for payload in consumed_payloads}
        anchor_transforms = {anchor.transform for anchor in anchors}
        availability: Dict[Tuple, List[InstancePayload]] = defaultdict(list)
        for payload in components:
            if payload.transform in consumed:
                continue
            if payload.transform in anchor_transforms:
                continue
            availability[self._component_signature(payload)].append(payload)
        for payloads in availability.values():
            payloads.sort(key=lambda value: value.world_position)
        return availability

    def _match_anchor_to_template_slots(
        self,
        anchor: InstancePayload,
        template_slots: Sequence[AssemblyTemplateSlot],
        availability: Dict[Tuple, List[InstancePayload]],
    ) -> Optional[Dict[int, InstancePayload]]:
        matches: Dict[int, InstancePayload] = {}
        for slot in template_slots:
            if slot.is_root:
                matches[slot.slot_id] = anchor
                continue
            candidates = availability.get(slot.signature, [])
            best_idx = None
            best_payload = None
            best_score = None
            for idx, payload in enumerate(list(candidates)):
                relative = self._relative_matrix(anchor.matrix, payload.matrix)
                score = self._matrix_difference_score(relative, slot.reference_matrix)
                if score is None:
                    continue
                if best_payload is None or score < best_score:
                    best_payload = payload
                    best_score = score
                    best_idx = idx
            if best_payload is None or best_idx is None:
                return None
            matches[slot.slot_id] = best_payload
            candidates.pop(best_idx)
        return matches

    def _descriptor_from_slot_mapping(
        self,
        anchor: InstancePayload,
        source_transform: pm.nodetypes.Transform,
        slot_payloads: Dict[int, InstancePayload],
        template_slots: Sequence[AssemblyTemplateSlot],
    ) -> AssemblyDescriptor:
        ordered_payloads: List[InstancePayload] = []
        for slot in template_slots:
            payload = slot_payloads.get(slot.slot_id)
            if payload is None:
                raise RuntimeError(
                    "Template slot %s missing payload for anchor %s"
                    % (slot.slot_id, anchor.transform)
                )
            ordered_payloads.append(payload)
        signature = tuple(
            sorted(
                self._assembly_component_signature(payload)
                for payload in ordered_payloads
            )
        )
        root_signature = self._component_signature(anchor)
        return AssemblyDescriptor(
            source_transform=source_transform,
            components=ordered_payloads,
            signature=signature,
            root_component=anchor,
            root_signature=root_signature,
            matched_slots=dict(slot_payloads),
        )

    def _descriptor_from_components(
        self,
        source_transform: pm.nodetypes.Transform,
        components: Sequence[InstancePayload],
    ) -> AssemblyDescriptor:
        signature = tuple(
            sorted(
                self._assembly_component_signature(payload) for payload in components
            )
        )
        root_component = max(components, key=self._payload_volume)
        return AssemblyDescriptor(
            source_transform=source_transform,
            components=list(components),
            signature=signature,
            root_component=root_component,
            root_signature=self._component_signature(root_component),
        )

    def _anchor_capture_radius(
        self,
        anchor: InstancePayload,
        components: Sequence[InstancePayload],
        assembly_count: int,
    ) -> float:
        longest_axis = max(anchor.bbox_size)
        scale_radius = max(longest_axis * self.anchor_capture_multiplier, 1.0)
        neighbor_radius = self._neighbor_radius(anchor, components, assembly_count)
        return max(scale_radius, neighbor_radius)

    def _neighbor_radius(
        self,
        anchor: InstancePayload,
        components: Sequence[InstancePayload],
        assembly_count: int,
    ) -> float:
        if assembly_count <= 0:
            return 1.0
        distances = [
            self._payload_distance(anchor, payload)
            for payload in components
            if payload is not anchor
        ]
        if not distances:
            return 1.0
        distances.sort()
        approx_components = max(
            int(math.ceil(len(components) / max(assembly_count, 1))), 1
        )
        neighbor_index = min(len(distances) - 1, max(approx_components - 1, 0))
        target_distance = distances[neighbor_index]
        return target_distance + self.template_position_tolerance

    def _payload_distance(
        self, payload_a: InstancePayload, payload_b: InstancePayload
    ) -> float:
        return math.dist(payload_a.world_position, payload_b.world_position)

    def _group_assemblies(
        self, assemblies: Iterable[AssemblyDescriptor]
    ) -> List[AssemblyGroup]:
        assemblies = list(assemblies)
        groups: List[AssemblyGroup] = []
        buckets: Dict[Tuple, List[AssemblyDescriptor]] = defaultdict(list)
        for descriptor in assemblies:
            if descriptor.signature:
                buckets[descriptor.signature].append(descriptor)

        assigned_ids: set[int] = set()

        for root_signature, bucket in buckets.items():
            if not bucket:
                continue
            reference = self._select_reference_assembly(bucket)
            template_slots = self._build_template_slots(reference)
            reference.matched_slots = {
                slot.slot_id: slot.prototype_payload for slot in template_slots
            }
            group = AssemblyGroup(
                prototype=reference,
                template_slots=template_slots,
            )
            assigned_ids.add(id(reference))

            for descriptor in bucket:
                if descriptor is reference:
                    continue
                matches = self._match_assembly_to_template(descriptor, template_slots)
                if matches is None:
                    continue
                descriptor.matched_slots = matches
                group.add_member(descriptor)
                assigned_ids.add(id(descriptor))

            groups.append(group)

        for descriptor in assemblies:
            if id(descriptor) not in assigned_ids:
                template_slots = self._build_template_slots(descriptor)
                descriptor.matched_slots = {
                    slot.slot_id: slot.prototype_payload for slot in template_slots
                }
                groups.append(
                    AssemblyGroup(
                        prototype=descriptor,
                        template_slots=template_slots,
                    )
                )

        return groups

    def _match_group(
        self, payload: InstancePayload, groups: Sequence[InstanceGroup]
    ) -> Optional[InstanceGroup]:
        for group in groups:
            if not self._materials_match(payload, group.prototype):
                continue
            if self._geometry_matches(payload, group.prototype):
                return group
        return None

    def _materials_match(
        self, payload: InstancePayload, prototype: InstancePayload
    ) -> bool:
        if not self.require_same_material:
            return True
        return payload.material_signature == prototype.material_signature

    def _geometry_matches(
        self, payload: InstancePayload, prototype: InstancePayload
    ) -> bool:
        if payload.vertex_count != prototype.vertex_count:
            return False

        size_a = payload.bbox_size
        size_b = prototype.bbox_size

        def _ratio(a: float, b: float) -> float:
            denom = max(max(a, b), 1e-6)
            return 1.0 - abs(a - b) / denom

        axis_similarity = sum(_ratio(size_a[i], size_b[i]) for i in range(3)) / 3.0
        volume_a = max(size_a[0] * size_a[1] * size_a[2], 1e-12)
        volume_b = max(size_b[0] * size_b[1] * size_b[2], 1e-12)
        volume_similarity = 1.0 - abs(volume_a - volume_b) / max(volume_a, volume_b)

        similarity = (axis_similarity + volume_similarity) * 0.5
        return similarity >= self.tolerance

    def _select_reference_assembly(
        self, assemblies: Sequence[AssemblyDescriptor]
    ) -> AssemblyDescriptor:
        return max(assemblies, key=lambda desc: len(desc.components))

    def _build_template_slots(
        self, descriptor: AssemblyDescriptor
    ) -> List[AssemblyTemplateSlot]:
        slots: List[AssemblyTemplateSlot] = []
        root_matrix = descriptor.root_component.matrix
        slot_id = 0
        for payload in descriptor.components:
            relative = self._relative_matrix(root_matrix, payload.matrix)
            slot = AssemblyTemplateSlot(
                slot_id=slot_id,
                signature=self._component_signature(payload),
                reference_matrix=relative,
                prototype_payload=payload,
                is_root=payload is descriptor.root_component,
            )
            slots.append(slot)
            slot_id += 1
        return slots

    def _match_assembly_to_template(
        self,
        descriptor: AssemblyDescriptor,
        template_slots: Sequence[AssemblyTemplateSlot],
    ) -> Optional[Dict[int, InstancePayload]]:
        root = descriptor.root_component
        available: Dict[Tuple, List[InstancePayload]] = defaultdict(list)
        for payload in descriptor.components:
            available[self._component_signature(payload)].append(payload)

        matches: Dict[int, InstancePayload] = {}
        for slot in template_slots:
            candidates = available.get(slot.signature, [])
            best_payload = None
            best_score = None
            for payload in list(candidates):
                relative = self._relative_matrix(root.matrix, payload.matrix)
                score = self._matrix_difference_score(relative, slot.reference_matrix)
                if score is None:
                    continue
                if best_payload is None or score < best_score:
                    best_payload = payload
                    best_score = score
            if best_payload is None:
                return None
            matches[slot.slot_id] = best_payload
            candidates.remove(best_payload)

        return matches

    def _relative_matrix(
        self, root_matrix: om.MMatrix, payload_matrix: om.MMatrix
    ) -> om.MMatrix:
        return Matrices.mult(Matrices.inverse(root_matrix), payload_matrix)

    def _matrix_difference_score(
        self, candidate: om.MMatrix, reference: om.MMatrix
    ) -> Optional[float]:
        translation_ok, translation_delta = self._translation_within_tolerance(
            candidate, reference
        )
        rotation_ok, rotation_delta = self._rotation_within_tolerance(
            candidate, reference
        )
        if not translation_ok or not rotation_ok:
            return None
        return translation_delta + rotation_delta / max(
            self.template_rotation_tolerance, 1e-3
        )

    def _translation_within_tolerance(
        self, candidate: om.MMatrix, reference: om.MMatrix
    ) -> Tuple[bool, float]:
        cand_t, _, _ = Matrices.decompose(candidate)
        ref_t, _, _ = Matrices.decompose(reference)
        delta = math.dist(cand_t, ref_t)
        return delta <= self.template_position_tolerance, delta

    def _rotation_within_tolerance(
        self, candidate: om.MMatrix, reference: om.MMatrix
    ) -> Tuple[bool, float]:
        _, cand_r, _ = Matrices.decompose(candidate)
        _, ref_r, _ = Matrices.decompose(reference)
        deltas = [self._angle_delta(cand_r[i], ref_r[i]) for i in range(3)]
        max_delta = max(abs(value) for value in deltas)
        return max_delta <= self.template_rotation_tolerance, max_delta

    def _angle_delta(self, angle_a: float, angle_b: float) -> float:
        delta = (angle_a - angle_b + 180.0) % 360.0 - 180.0
        return delta

    def _component_signature(self, payload: InstancePayload) -> Tuple:
        bbox = tuple(round(size, 4) for size in payload.bbox_size)
        return (payload.vertex_count, bbox, payload.material_signature)

    def _payload_volume(self, payload: InstancePayload) -> float:
        size = payload.bbox_size
        return max(size[0], 1e-4) * max(size[1], 1e-4) * max(size[2], 1e-4)

    def _matrix_signature(self, matrix: om.MMatrix) -> Tuple:
        translation, rotation, scale = Matrices.decompose(matrix)
        t_sig = tuple(round(value, 4) for value in translation)
        r_sig = tuple(round(value, 2) for value in rotation)
        s_sig = tuple(round(value, 4) for value in scale)
        return t_sig + r_sig + s_sig

    def _assembly_component_signature(self, payload: InstancePayload) -> Tuple:
        return (
            self._component_signature(payload),
            self._matrix_signature(payload.local_matrix),
        )

    def _log_summary(self, result: InstanceSeparationResult) -> None:
        instantiable = len(result.instantiable_groups)
        uniques = len(result.unique_groups)
        assembly_instantiable = len(result.instantiable_assembly_groups)
        assembly_unique = len(result.unique_assemblies)
        self.logger.info(
            "InstanceSeparator processed %s payloads → %s instantiable groups, %s unique",
            result.payload_count,
            instantiable,
            uniques,
        )
        for group in result.instantiable_groups:
            self.logger.info(
                " - Prototype %s has %s duplicates",
                group.prototype.transform,
                len(group.members),
            )
        if assembly_instantiable:
            self.logger.info(
                "Assemblies: %s instantiable groups, %s unique",
                assembly_instantiable,
                assembly_unique,
            )

    def _rebuild_instantiable_assemblies(
        self, result: InstanceSeparationResult
    ) -> None:
        for group in result.instantiable_assembly_groups:
            targets = [group.prototype] + list(group.members)
            for descriptor in targets:
                self._rebuild_single_assembly(group, descriptor)

    def _rebuild_single_assembly(
        self, group: AssemblyGroup, target: AssemblyDescriptor
    ) -> None:
        if not group.template_slots:
            return

        for slot in group.template_slots:
            target_payload = target.matched_slots.get(slot.slot_id)
            prototype_payload = slot.prototype_payload
            if not target_payload or not prototype_payload:
                continue
            if target_payload.transform == prototype_payload.transform:
                continue

            try:
                new_instance = pm.instance(prototype_payload.transform)[0]
            except RuntimeError:
                self.logger.warning(
                    "Failed to instance prototype %s for component %s",
                    prototype_payload.transform,
                    target_payload.transform,
                )
                continue

            Matrices.bake_world_matrix_to_transform(new_instance, target_payload.matrix)
            if target_payload.parent:
                try:
                    pm.parent(new_instance, target_payload.parent, absolute=True)
                except RuntimeError:
                    pass
            new_instance.visibility.set(target_payload.visibility)
            try:
                pm.delete(target_payload.transform)
            except RuntimeError:
                pass
            try:
                new_instance.rename(target_payload.transform.name())
            except RuntimeError:
                pass

            target_payload.transform = new_instance
            shape = NodeUtils.get_shape_node(new_instance, returned_type="obj")
            if isinstance(shape, list):
                shape = shape[0] if shape else None
            target_payload.shape = shape
            target_payload.matrix = Matrices.to_mmatrix(new_instance)

        if self.collapse_rebuilt_assemblies:
            self._collapse_assembly_components(target)

    def _collapse_assembly_components(self, descriptor: AssemblyDescriptor) -> None:
        transforms = []
        for payload in descriptor.matched_slots.values():
            transform = payload.transform if payload else None
            if not transform:
                continue
            if not pm.objExists(transform):
                continue
            if transform in transforms:
                continue
            transforms.append(transform)

        if len(transforms) <= 1:
            return

        parent = None
        target_name = None
        if descriptor.source_transform and pm.objExists(descriptor.source_transform):
            parent = descriptor.source_transform.getParent()
            target_name = descriptor.source_transform.name()

        try:
            unite_result = pm.polyUnite(transforms, mergeUVSets=True, ch=False)
        except RuntimeError:
            self.logger.warning(
                "Failed to collapse components for assembly %s",
                descriptor.source_transform,
            )
            return

        combined = (
            unite_result[0] if isinstance(unite_result, (list, tuple)) else unite_result
        )
        if not isinstance(combined, pm.nodetypes.Transform):
            try:
                combined = pm.PyNode(combined)
            except pm.MayaNodeError:
                return

        try:
            pm.delete(combined, ch=True)
        except RuntimeError:
            pass
        try:
            pm.makeIdentity(combined, apply=True, t=1, r=1, s=1, n=0)
        except RuntimeError:
            pass

        if parent:
            try:
                pm.parent(combined, parent, absolute=True)
            except RuntimeError:
                pass

        for transform in transforms:
            if transform == combined:
                continue
            if not pm.objExists(transform):
                continue
            try:
                pm.delete(transform)
            except RuntimeError:
                pass

        if target_name:
            try:
                combined.rename(target_name)
            except RuntimeError:
                pass

        self._component_to_source[combined] = combined
        self._source_world_mats[combined] = Matrices.to_mmatrix(combined)

        descriptor.source_transform = combined
        payload = self._build_payload(combined)
        if not payload:
            descriptor.components = []
            descriptor.matched_slots = {}
            return

        descriptor.components = [payload]
        descriptor.root_component = payload
        descriptor.root_signature = self._component_signature(payload)
        descriptor.signature = (self._assembly_component_signature(payload),)
        descriptor.matched_slots = {0: payload}


__all__ = [
    "InstancePayload",
    "InstanceGroup",
    "InstanceSeparationResult",
    "InstanceSeparator",
    "AssemblyDescriptor",
    "AssemblyGroup",
    "AssemblyTemplateSlot",
]


if __name__ == "__main__":
    separator = InstanceSeparator(
        tolerance=0.98,
        require_same_material=True,
        split_shells=True,
        rebuild_instances=True,
        verbose=True,
    )
    objects = pm.selected()
    result = separator.separate(objects)
