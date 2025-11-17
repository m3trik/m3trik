from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Sequence, Union
from enum import Enum
import pymel.core as pm


# ===============================================================================
# Core Data Structures
# ===============================================================================


@dataclass(frozen=True)
class TimeRange:
    """Immutable time range for animation with interpolation utilities."""

    start_frame: int
    end_frame: int

    def __post_init__(self):
        if self.start_frame >= self.end_frame:
            raise ValueError(
                f"Invalid time range: {self.start_frame} >= {self.end_frame}"
            )

    @property
    def duration_frames(self) -> int:
        """Duration in frames."""
        return self.end_frame - self.start_frame

    def normalize_frame_to_weight(self, frame: int) -> float:
        """Convert frame position to normalized weight (0.0-1.0)."""
        if frame <= self.start_frame:
            return 0.0
        if frame >= self.end_frame:
            return 1.0
        progress = (frame - self.start_frame) / self.duration_frames
        return round(progress, 3)

    def denormalize_weight_to_frame(self, weight: float) -> int:
        """Convert normalized weight to frame position."""
        weight = max(0.0, min(1.0, weight))
        return int(self.start_frame + (weight * self.duration_frames))

    def contains_frame(self, frame: int) -> bool:
        """Check if frame falls within time range."""
        return self.start_frame <= frame <= self.end_frame

    @classmethod
    def from_blendshape_keyframes(cls, blendshape_node: pm.PyNode) -> TimeRange:
        """Extract time range from blendShape keyframe data."""
        keyframe_times = pm.keyframe(f"{blendshape_node}.weight[0]", query=True)
        if not keyframe_times or len(keyframe_times) < 2:
            raise ValueError(f"Insufficient keyframe data in {blendshape_node}")
        return cls(int(min(keyframe_times)), int(max(keyframe_times)))

    @classmethod
    def from_weight_attr(cls, weight_attr: str) -> TimeRange:
        """Extract time range from specific weight attribute (weight-index aware)."""
        keyframe_times = pm.keyframe(weight_attr, query=True)
        if not keyframe_times or len(keyframe_times) < 2:
            raise ValueError(f"Insufficient keyframe data on {weight_attr}")
        return cls(int(min(keyframe_times)), int(max(keyframe_times)))


@dataclass
class CorrectiveShape:
    """Represents a corrective blendShape target with comprehensive metadata."""

    geometry_node: pm.PyNode
    deformation_weight: float = field(init=False)
    blendshape_node_name: str = field(init=False)
    base_geometry_name: str = field(init=False)
    creation_frame: Optional[int] = field(init=False)

    def __post_init__(self):
        """Initialize metadata from geometry node attributes."""
        self._validate_corrective_attributes()
        self.deformation_weight = self._extract_weight()
        self.blendshape_node_name = self._extract_blendshape_reference()
        self.base_geometry_name = self._extract_base_reference()
        self.creation_frame = self._extract_frame_reference()

    def _validate_corrective_attributes(self) -> None:
        """Ensure geometry has required corrective shape attributes."""
        required_attributes = [
            "isCorrectiveShape",
            "deformationWeight",
            "blendShapeReference",
            "baseGeometryReference",
        ]
        missing_attrs = [
            attr for attr in required_attributes if not self.geometry_node.hasAttr(attr)
        ]
        if missing_attrs:
            raise ValueError(
                f"Geometry {self.geometry_node} missing attributes: {missing_attrs}"
            )

    def _extract_weight(self) -> float:
        return round(float(pm.getAttr(f"{self.geometry_node}.deformationWeight")), 3)

    def _extract_blendshape_reference(self) -> str:
        return str(pm.getAttr(f"{self.geometry_node}.blendShapeReference"))

    def _extract_base_reference(self) -> str:
        return str(pm.getAttr(f"{self.geometry_node}.baseGeometryReference"))

    def _extract_frame_reference(self) -> Optional[int]:
        if self.geometry_node.hasAttr("creationFrame"):
            return int(pm.getAttr(f"{self.geometry_node}.creationFrame"))
        return None

    def update_node_references(
        self, new_blendshape: pm.PyNode, new_base: pm.PyNode
    ) -> None:
        """Update corrective's node references for new deformation system."""
        pm.setAttr(
            f"{self.geometry_node}.blendShapeReference",
            str(new_blendshape),
            type="string",
        )
        pm.setAttr(
            f"{self.geometry_node}.baseGeometryReference", str(new_base), type="string"
        )
        self.blendshape_node_name = str(new_blendshape)
        self.base_geometry_name = str(new_base)


class InterpolationMode(Enum):
    """Enumeration of corrective shape creation methods."""

    WEIGHT_BASED = "weight_interpolation"
    TEMPORAL_BASED = "temporal_interpolation"


# ===============================================================================
# Geometry Validation and Utilities
# ===============================================================================


class GeometryValidator:
    """Comprehensive geometry validation for deformation systems."""

    @staticmethod
    def validate_mesh_transform(node: pm.PyNode) -> pm.nt.Transform:
        """Ensure node is a valid polygon mesh transform."""
        if not hasattr(node, "getShape"):
            raise TypeError(f"{node} is not a transform node")

        shape_node = node.getShape()
        if not shape_node or not isinstance(shape_node, pm.nodetypes.Mesh):
            raise TypeError(f"{node} does not contain polygon mesh geometry")
        return node

    @staticmethod
    def get_vertex_count(mesh_transform: pm.PyNode) -> int:
        """Extract vertex count from mesh geometry."""
        validated_mesh = GeometryValidator.validate_mesh_transform(mesh_transform)
        return validated_mesh.getShape().numVertices()

    @staticmethod
    def ensure_topology_compatibility(*mesh_transforms: pm.PyNode) -> None:
        """Verify all meshes have identical vertex topology."""
        if len(mesh_transforms) < 2:
            return

        vertex_counts = [
            GeometryValidator.get_vertex_count(mesh) for mesh in mesh_transforms
        ]

        if len(set(vertex_counts)) > 1:
            mesh_info = [
                f"{mesh}({count})"
                for mesh, count in zip(mesh_transforms, vertex_counts)
            ]
            raise ValueError(f"Topology mismatch: {', '.join(mesh_info)}")

    @staticmethod
    def validate_blendshape_node(blendshape_node: pm.PyNode) -> bool:
        """Validate blendShape deformer configuration."""
        if not pm.objExists(blendshape_node):
            raise ValueError(f"BlendShape node {blendshape_node} does not exist")

        # Verify envelope setting
        envelope_value = pm.getAttr(f"{blendshape_node}.envelope")
        if envelope_value != 1.0:
            pm.warning(f"BlendShape envelope is {envelope_value}, should be 1.0")

        # Check weight attribute accessibility
        if pm.getAttr(f"{blendshape_node}.weight[0]", lock=True):
            pm.warning(f"BlendShape weight attribute is locked")

        return True


class DeformationMath:
    """Mathematical utilities for deformation weight calculations."""

    MAYA_PRECISION = 3  # Maya's floating-point precision for weights

    @classmethod
    def normalize_weight(cls, weight: float) -> float:
        """Normalize weight to Maya-compatible precision."""
        return round(float(weight), cls.MAYA_PRECISION)

    @classmethod
    def generate_weight_distribution(
        cls,
        sample_count: int,
        weight_min: float = 0.0,
        weight_max: float = 1.0,
        include_bounds: bool = False,
    ) -> List[float]:
        """Generate evenly distributed weight values."""
        if sample_count <= 0:
            return []

        if include_bounds:
            if sample_count == 1:
                return [cls.normalize_weight((weight_min + weight_max) / 2)]
            step_size = (weight_max - weight_min) / (sample_count - 1)
            weights = [weight_min + step_size * i for i in range(sample_count)]
        else:
            step_size = (weight_max - weight_min) / (sample_count + 1)
            weights = [weight_min + step_size * (i + 1) for i in range(sample_count)]

        return [cls.normalize_weight(w) for w in weights]

    @classmethod
    def clamp_weight(cls, weight: float) -> float:
        """Clamp weight to valid deformation range."""
        return cls.normalize_weight(max(0.0, min(1.0, weight)))


class AssetOrganizer:
    """Scene organization and asset management for deformation workflows."""

    ORGANIZATION_GROUPS = {
        "correctives": "_deformationCorrectiveShapes_GRP",
        "sources": "_deformationSourceGeometry_GRP",
        "targets": "_deformationTargetGeometry_GRP",
        "archive": "_deformationArchive_GRP",
        "temp": "_deformationTemporary_GRP",
    }

    @classmethod
    def ensure_organization_group(cls, group_name: str) -> pm.nt.Transform:
        """Create or retrieve organizational group."""
        if pm.objExists(group_name):
            return pm.PyNode(group_name)

        # Create group with proper organization
        group = pm.group(empty=True, name=group_name)

        # Set group attributes for identification
        if not group.hasAttr("isDeformationGroup"):
            pm.addAttr(
                group,
                longName="isDeformationGroup",
                attributeType="bool",
                defaultValue=True,
            )

        # Color code groups for visual organization
        group_colors = {
            cls.ORGANIZATION_GROUPS["correctives"]: 13,  # Red - for correctives
            cls.ORGANIZATION_GROUPS["sources"]: 14,  # Green - for source geometry
            cls.ORGANIZATION_GROUPS["targets"]: 18,  # Cyan - for target geometry
            cls.ORGANIZATION_GROUPS["archive"]: 1,  # Black - for archived items
            cls.ORGANIZATION_GROUPS["temp"]: 17,  # Yellow - for temporary items
        }

        if group_name in group_colors:
            group.overrideEnabled.set(True)
            group.overrideColor.set(group_colors[group_name])

        pm.displayInfo(f"Created organization group: {group_name}")
        return group

    @classmethod
    def organize_corrective_shapes(
        cls, corrective_nodes: Sequence[pm.PyNode]
    ) -> pm.nt.Transform:
        """Organize corrective shapes into structured hierarchy."""
        correctives_group = cls.ensure_organization_group(
            cls.ORGANIZATION_GROUPS["correctives"]
        )

        organized_count = 0
        for node in corrective_nodes:
            if node.getParent() != correctives_group:
                pm.parent(node, correctives_group)
                organized_count += 1

        if organized_count > 0:
            pm.displayInfo(
                f"Organized {organized_count} corrective shapes into {correctives_group}"
            )

        return correctives_group

    @classmethod
    def organize_target_geometry(
        cls, target_nodes: Sequence[pm.PyNode]
    ) -> pm.nt.Transform:
        """Organize target geometry into structured hierarchy."""
        targets_group = cls.ensure_organization_group(
            cls.ORGANIZATION_GROUPS["targets"]
        )

        organized_count = 0
        for node in target_nodes:
            if node.getParent() != targets_group:
                pm.parent(node, targets_group)
                organized_count += 1

        if organized_count > 0:
            pm.displayInfo(
                f"Organized {organized_count} target geometries into {targets_group}"
            )

        return targets_group

    @classmethod
    def organize_source_geometry(
        cls, source_nodes: Sequence[pm.PyNode]
    ) -> pm.nt.Transform:
        """Organize source geometry into structured hierarchy."""
        sources_group = cls.ensure_organization_group(
            cls.ORGANIZATION_GROUPS["sources"]
        )

        organized_count = 0
        for node in source_nodes:
            if node.getParent() != sources_group:
                pm.parent(node, sources_group)
                organized_count += 1

        if organized_count > 0:
            pm.displayInfo(
                f"Organized {organized_count} source geometries into {sources_group}"
            )

        return sources_group

    @classmethod
    def organize_temporary_geometry(
        cls, temp_nodes: Sequence[pm.PyNode]
    ) -> pm.nt.Transform:
        """Organize temporary geometry into structured hierarchy."""
        temp_group = cls.ensure_organization_group(cls.ORGANIZATION_GROUPS["temp"])

        organized_count = 0
        for node in temp_nodes:
            if node.getParent() != temp_group:
                pm.parent(node, temp_group)
                organized_count += 1

        if organized_count > 0:
            pm.displayInfo(
                f"Organized {organized_count} temporary items into {temp_group}"
            )

        return temp_group

    @classmethod
    def archive_geometry_node(cls, geometry_node: pm.PyNode) -> None:
        """Move geometry to archive group."""
        archive_group = cls.ensure_organization_group(
            cls.ORGANIZATION_GROUPS["archive"]
        )

        if geometry_node.getParent() != archive_group:
            pm.parent(geometry_node, archive_group)
            # Hide archived items
            geometry_node.visibility.set(False)
            pm.displayInfo(f"Archived: {geometry_node}")

    @classmethod
    def cleanup_empty_organization(cls) -> int:
        """Remove empty organizational groups from scene."""
        removed_count = 0
        for group_name in cls.ORGANIZATION_GROUPS.values():
            if pm.objExists(group_name):
                group_node = pm.PyNode(group_name)
                child_nodes = pm.listRelatives(group_node, children=True) or []
                if not child_nodes:
                    pm.delete(group_node)
                    removed_count += 1
                    pm.displayInfo(f"Removed empty group: {group_name}")
        return removed_count

    @classmethod
    def cleanup_temporary_objects(cls) -> int:
        """Clean up all temporary objects and groups."""
        cleaned_count = 0

        # Clean temporary group contents
        temp_group_name = cls.ORGANIZATION_GROUPS["temp"]
        if pm.objExists(temp_group_name):
            temp_group = pm.PyNode(temp_group_name)
            temp_objects = pm.listRelatives(temp_group, children=True) or []

            for obj in temp_objects:
                pm.delete(obj)
                cleaned_count += 1

            # Remove the empty group
            if not pm.listRelatives(temp_group, children=True):
                pm.delete(temp_group)

        pm.displayInfo(f"Cleaned up {cleaned_count} temporary objects")
        return cleaned_count

    @classmethod
    def organize_all_workflow_objects(cls, workflow_instance) -> None:
        """Organize all objects created by a workflow instance."""
        if not workflow_instance._workflow_initialized:
            return

        # Organize target geometry
        if workflow_instance.deformation_controller:
            target_geo = workflow_instance.deformation_controller.target_geometry
            cls.organize_target_geometry([target_geo])

        # Organize correctives
        correctives = CorrectiveManager.discover_scene_correctives()
        if correctives:
            corrective_nodes = [c.geometry_node for c in correctives]
            cls.organize_corrective_shapes(corrective_nodes)

        pm.displayInfo("All workflow objects organized into proper groups")

    @classmethod
    def get_organization_summary(cls) -> Dict[str, int]:
        """Get summary of organized objects."""
        summary = {}

        for category, group_name in cls.ORGANIZATION_GROUPS.items():
            count = 0
            if pm.objExists(group_name):
                group_node = pm.PyNode(group_name)
                children = pm.listRelatives(group_node, children=True) or []
                count = len(children)
            summary[category] = count

        return summary


class GeometryOperations:
    """Low-level geometry operations for deformation workflows."""

    @staticmethod
    def create_clean_duplicate(
        source_mesh: pm.PyNode, duplicate_name: str
    ) -> pm.nt.Transform:
        """Create geometry duplicate without construction history."""
        duplicate_node = pm.duplicate(
            source_mesh, name=duplicate_name, returnRootsOnly=True
        )[0]
        pm.delete(duplicate_node, constructionHistory=True)
        return duplicate_node

    @staticmethod
    def apply_corrective_metadata(
        geometry_node: pm.PyNode,
        deformation_weight: float,
        blendshape_node: pm.PyNode,
        base_geometry: pm.PyNode,
        creation_frame: Optional[int] = None,
    ) -> None:
        """Apply comprehensive metadata to corrective shape geometry."""
        metadata_attributes = {
            "isCorrectiveShape": (True, "bool"),
            "deformationWeight": (deformation_weight, "double"),
            "blendShapeReference": (str(blendshape_node), "string"),
            "baseGeometryReference": (str(base_geometry), "string"),
        }

        if creation_frame is not None:
            metadata_attributes["creationFrame"] = (creation_frame, "long")

        for attribute_name, (value, data_type) in metadata_attributes.items():
            if not geometry_node.hasAttr(attribute_name):
                if data_type == "string":
                    pm.addAttr(
                        geometry_node, longName=attribute_name, dataType="string"
                    )
                else:
                    pm.addAttr(
                        geometry_node,
                        longName=attribute_name,
                        attributeType=data_type,
                        keyable=False,
                    )

            if data_type == "string":
                pm.setAttr(
                    f"{geometry_node}.{attribute_name}", str(value), type="string"
                )
            else:
                pm.setAttr(f"{geometry_node}.{attribute_name}", value)


# ===============================================================================
# Core Deformation System Classes
# ===============================================================================


class DeformationController:
    """Controls blendShape deformer operations and keyframe animation."""

    def __init__(
        self,
        base_geometry: pm.PyNode,
        target_geometry: pm.PyNode,
        blendshape_node: pm.PyNode,
    ):
        self.base_geometry = GeometryValidator.validate_mesh_transform(base_geometry)
        self.target_geometry = GeometryValidator.validate_mesh_transform(
            target_geometry
        )
        self.blendshape_node = blendshape_node

        GeometryValidator.ensure_topology_compatibility(
            self.base_geometry, self.target_geometry
        )
        GeometryValidator.validate_blendshape_node(self.blendshape_node)

        # Resolve and cache target index and weight attribute
        self.target_index: int = self._resolve_target_index()
        self.weight_attr: str = f"{self.blendshape_node}.weight[{self.target_index}]"

    def _resolve_target_index(self) -> int:
        """Resolve the blendShape target index for self.target_geometry."""
        # Get alias pairs from blendShape node
        alias_pairs = pm.aliasAttr(self.blendshape_node, query=True) or []
        alias_to_index = {}

        # Parse alias pairs into dictionary
        for i in range(0, len(alias_pairs), 2):
            if i + 1 < len(alias_pairs):
                alias_name = alias_pairs[i]
                weight_attr = alias_pairs[i + 1]
                # Extract index from weight[N] format
                try:
                    index = int(weight_attr.split("[")[-1].split("]")[0])
                    alias_to_index[alias_name] = index
                except (ValueError, IndexError):
                    continue

        target_alias = str(self.target_geometry)
        if target_alias in alias_to_index:
            return alias_to_index[target_alias]

        # Target missing: add it and create alias
        next_index = len(alias_to_index)
        pm.blendShape(
            self.blendshape_node,
            edit=True,
            target=(self.base_geometry, next_index, self.target_geometry, 1.0),
        )

        # Try to create alias (may fail if name conflicts exist)
        try:
            pm.aliasAttr(target_alias, f"{self.blendshape_node}.weight[{next_index}]")
        except Exception:
            pass  # Alias creation is optional

        return next_index

    def get_current_weight(self) -> float:
        """Query current blendShape deformation weight."""
        return float(pm.getAttr(self.weight_attr))

    def set_deformation_weight(self, weight: float) -> None:
        """Set blendShape deformation weight with validation."""
        validated_weight = DeformationMath.clamp_weight(weight)
        pm.setAttr(self.weight_attr, validated_weight)

    def create_linear_keyframe_animation(self, time_range: TimeRange) -> None:
        """Establish linear keyframe interpolation across time range."""
        # Clear existing keyframe data
        pm.cutKey(
            self.blendshape_node, attribute=f"weight[{self.target_index}]", clear=True
        )

        # Set start keyframe (zero deformation)
        pm.currentTime(time_range.start_frame)
        pm.setKeyframe(
            self.blendshape_node,
            attribute=f"weight[{self.target_index}]",
            value=0.0,
            time=time_range.start_frame,
        )

        # Set end keyframe (full deformation)
        pm.currentTime(time_range.end_frame)
        pm.setKeyframe(
            self.blendshape_node,
            attribute=f"weight[{self.target_index}]",
            value=1.0,
            time=time_range.end_frame,
        )

        # Configure linear tangent interpolation
        pm.keyTangent(
            self.blendshape_node,
            attribute=f"weight[{self.target_index}]",
            time=(time_range.start_frame, time_range.end_frame),
            inTangentType="linear",
            outTangentType="linear",
        )

    def test_deformation_preview(self, preview_weight: float = 0.5) -> bool:
        """Preview deformation by temporarily setting weight value."""
        original_weight = self.get_current_weight()
        try:
            self.set_deformation_weight(preview_weight)
            pm.refresh()
            return True
        finally:
            self.set_deformation_weight(original_weight)

    def extract_animation_time_range(self) -> TimeRange:
        """Extract time range from existing keyframe animation."""
        return TimeRange.from_weight_attr(self.weight_attr)

    @classmethod
    def create_deformation_system(
        cls,
        base_geometry: pm.PyNode,
        target_geometry: pm.PyNode,
        system_name: str = "deformationSystem",
    ) -> DeformationController:
        """Create new blendShape deformation system with proper configuration."""
        GeometryValidator.ensure_topology_compatibility(base_geometry, target_geometry)

        # Check for existing blendShape deformer
        deformation_history = base_geometry.listHistory(type="blendShape")
        if deformation_history:
            blendshape_node = deformation_history[0]
        else:
            blendshape_node = pm.blendShape(
                target_geometry,
                base_geometry,
                name=system_name,
                frontOfChain=True,
                origin="world",
            )[0]

        # Configure deformer attributes
        pm.setAttr(f"{blendshape_node}.envelope", 1.0)
        pm.setAttr(f"{blendshape_node}.weight[0]", keyable=True, lock=False)

        # Create controller which will resolve/alias target index
        controller = cls(base_geometry, target_geometry, blendshape_node)
        return controller


class CorrectiveShapeFactory:
    """Factory for creating corrective shapes using various interpolation methods."""

    def __init__(self, deformation_controller: DeformationController):
        self.deformation_controller = deformation_controller

    def create_weight_based_correctives(
        self, weight_values: Sequence[float], naming_prefix: str = "corrective"
    ) -> List[CorrectiveShape]:
        """Create corrective shapes at specific deformation weights."""
        original_weight = self.deformation_controller.get_current_weight()
        created_correctives = []

        try:
            for weight in weight_values:
                normalized_weight = DeformationMath.clamp_weight(weight)

                # Apply deformation at target weight
                self.deformation_controller.set_deformation_weight(normalized_weight)
                pm.refresh()

                # Capture deformed geometry state
                corrective_name = (
                    f"{naming_prefix}_w{int(normalized_weight * 1000):03d}"
                )
                corrective_geometry = GeometryOperations.create_clean_duplicate(
                    self.deformation_controller.base_geometry, corrective_name
                )

                # Reset to neutral for blendShape target creation
                self.deformation_controller.set_deformation_weight(0.0)
                pm.refresh()

                # Register as blendShape intermediate target using correct target index
                pm.blendShape(
                    self.deformation_controller.blendshape_node,
                    edit=True,
                    inBetween=True,
                    target=(
                        self.deformation_controller.base_geometry,
                        self.deformation_controller.target_index,
                        corrective_geometry,
                        normalized_weight,
                    ),
                )

                # Apply metadata and create corrective shape object
                GeometryOperations.apply_corrective_metadata(
                    corrective_geometry,
                    normalized_weight,
                    self.deformation_controller.blendshape_node,
                    self.deformation_controller.base_geometry,
                )

                corrective_shape = CorrectiveShape(corrective_geometry)
                created_correctives.append(corrective_shape)

        finally:
            self.deformation_controller.set_deformation_weight(original_weight)

        # Organize created correctives
        AssetOrganizer.organize_corrective_shapes(
            [c.geometry_node for c in created_correctives]
        )

        return created_correctives

    def create_temporal_correctives(
        self, frame_positions: Sequence[int], naming_prefix: str = "temporal"
    ) -> List[CorrectiveShape]:
        """Create corrective shapes at specific animation frames."""
        animation_range = self.deformation_controller.extract_animation_time_range()
        original_weight = self.deformation_controller.get_current_weight()
        original_time = pm.currentTime(query=True)
        created_correctives = []

        try:
            for frame_position in frame_positions:
                if not animation_range.contains_frame(frame_position):
                    pm.warning(
                        f"Frame {frame_position} outside animation range "
                        f"{animation_range.start_frame}-{animation_range.end_frame}"
                    )
                    continue

                interpolated_weight = animation_range.normalize_frame_to_weight(
                    frame_position
                )

                # Set time and evaluate deformation
                pm.currentTime(frame_position)
                self.deformation_controller.set_deformation_weight(interpolated_weight)
                pm.refresh()

                # Capture temporal geometry state
                corrective_name = f"{naming_prefix}_f{frame_position}_w{int(interpolated_weight * 1000):03d}"
                corrective_geometry = GeometryOperations.create_clean_duplicate(
                    self.deformation_controller.base_geometry, corrective_name
                )

                # Reset for target registration
                self.deformation_controller.set_deformation_weight(0.0)
                pm.refresh()

                # Register as blendShape intermediate target using correct target index
                pm.blendShape(
                    self.deformation_controller.blendshape_node,
                    edit=True,
                    inBetween=True,
                    target=(
                        self.deformation_controller.base_geometry,
                        self.deformation_controller.target_index,
                        corrective_geometry,
                        interpolated_weight,
                    ),
                )

                # Apply metadata with frame information
                GeometryOperations.apply_corrective_metadata(
                    corrective_geometry,
                    interpolated_weight,
                    self.deformation_controller.blendshape_node,
                    self.deformation_controller.base_geometry,
                    frame_position,
                )

                corrective_shape = CorrectiveShape(corrective_geometry)
                created_correctives.append(corrective_shape)

        finally:
            self.deformation_controller.set_deformation_weight(original_weight)
            pm.currentTime(original_time)

        # Organize created correctives
        AssetOrganizer.organize_corrective_shapes(
            [c.geometry_node for c in created_correctives]
        )

        return created_correctives


class CorrectiveManager:
    """Manages collections of corrective shapes and applies modifications."""

    LEGACY_GROUP_NAMES = [
        "_deformationCorrectiveShapes_GRP",
        "_blendTargets_GRP",
        "_morphInbetweens_GRP",
        "_preciseTweens_GRP",
    ]

    @classmethod
    def discover_scene_correctives(cls) -> List[CorrectiveShape]:
        """Discover all corrective shapes present in the scene."""
        corrective_nodes = []
        discovered_nodes = set()

        # Search organized groups
        for group_name in cls.LEGACY_GROUP_NAMES:
            if pm.objExists(group_name):
                group_children = (
                    pm.listRelatives(group_name, children=True, type="transform") or []
                )
                corrective_nodes.extend(group_children)

        # Search loose corrective shapes
        loose_correctives = [
            node
            for node in pm.ls(type="transform")
            if node.hasAttr("isCorrectiveShape")
        ]
        corrective_nodes.extend(loose_correctives)

        # Remove duplicates and validate
        validated_correctives = []
        for node in corrective_nodes:
            if node in discovered_nodes:
                continue
            discovered_nodes.add(node)

            if node.hasAttr("isCorrectiveShape") and pm.getAttr(
                f"{node}.isCorrectiveShape"
            ):
                try:
                    validated_correctives.append(CorrectiveShape(node))
                except ValueError:
                    pm.warning(f"Invalid corrective shape: {node}")
                    continue

        return sorted(validated_correctives, key=lambda c: c.deformation_weight)

    @classmethod
    def group_correctives_by_weight(
        cls, correctives: Sequence[CorrectiveShape]
    ) -> Dict[float, List[CorrectiveShape]]:
        """Group corrective shapes by deformation weight values."""
        weight_groups = {}
        for corrective in correctives:
            weight = corrective.deformation_weight
            weight_groups.setdefault(weight, []).append(corrective)
        return dict(sorted(weight_groups.items()))

    @classmethod
    def apply_corrective_modifications(
        cls,
        deformation_controller: DeformationController,
        correctives: Optional[Sequence[CorrectiveShape]] = None,
        skip_weight_conflicts: bool = True,
    ) -> List[CorrectiveShape]:
        """Apply corrective shape modifications to deformation system."""
        if correctives is None:
            correctives = cls.discover_scene_correctives()

        if not correctives:
            return []

        weight_groups = cls.group_correctives_by_weight(correctives)
        applied_correctives = []
        original_weight = deformation_controller.get_current_weight()

        try:
            for weight, corrective_group in weight_groups.items():
                # Use most recent corrective for each weight
                primary_corrective = corrective_group[-1]

                if len(corrective_group) > 1 and not skip_weight_conflicts:
                    pm.warning(
                        f"Multiple correctives at weight {weight}, "
                        f"using: {primary_corrective.geometry_node}"
                    )

                try:
                    pm.blendShape(
                        deformation_controller.blendshape_node,
                        edit=True,
                        inBetween=True,
                        target=(
                            deformation_controller.base_geometry,
                            deformation_controller.target_index,
                            primary_corrective.geometry_node,
                            float(weight),
                        ),
                    )
                    applied_correctives.append(primary_corrective)
                except Exception as e:
                    if "Weights must be unique" in str(e) and skip_weight_conflicts:
                        continue  # Skip conflicting weights
                    else:
                        pm.warning(
                            f"Failed to apply {primary_corrective.geometry_node}: {e}"
                        )

        finally:
            deformation_controller.set_deformation_weight(original_weight)

        return applied_correctives

    @classmethod
    def update_corrective_references(
        cls, new_blendshape: pm.PyNode, new_base_geometry: pm.PyNode
    ) -> List[CorrectiveShape]:
        """Update all corrective references for new deformation system."""
        correctives = cls.discover_scene_correctives()
        for corrective in correctives:
            corrective.update_node_references(new_blendshape, new_base_geometry)
        return correctives


# ===============================================================================
# Main Workflow Orchestration
# ===============================================================================


class BlendShapeDeformationWorkflow:
    """
    Comprehensive workflow orchestrator for blendShape deformation systems.

    Provides unified interface for creating, editing, and managing complete
    deformation workflows with corrective shape support and temporal interpolation.
    """

    def __init__(self):
        self.deformation_controller: Optional[DeformationController] = None
        self.corrective_factory: Optional[CorrectiveShapeFactory] = None
        self._workflow_initialized = False

    # ===========================================================================
    # Primary Workflow Operations
    # ===========================================================================

    def initialize_deformation_system(
        self,
        base_geometry: Optional[pm.PyNode] = None,
        target_geometry: Optional[pm.PyNode] = None,
        animation_range: Union[TimeRange, Tuple[int, int]] = (5500, 5800),
        system_name: str = "deformationSystem",
        enable_preview: bool = True,
    ) -> bool:
        """
        Initialize complete deformation system from base and target geometry.

        Args:
            base_geometry: Mesh that receives deformation
            target_geometry: Mesh defining deformation result
            animation_range: Time range for keyframe animation
            system_name: Name for blendShape deformer node
            enable_preview: Whether to preview deformation after setup

        Returns:
            bool: True if initialization successful
        """
        try:
            # Handle selection-based input
            if base_geometry is None or target_geometry is None:
                selection = pm.selected()
                if len(selection) != 2:
                    pm.error(
                        "Please select exactly 2 meshes or provide both parameters"
                    )
                    return False
                base_geometry, target_geometry = selection

            # Convert time range if needed
            if isinstance(animation_range, tuple):
                animation_range = TimeRange(*animation_range)

            # Create deformation controller
            self.deformation_controller = (
                DeformationController.create_deformation_system(
                    base_geometry, target_geometry, system_name
                )
            )

            # Configure keyframe animation
            self.deformation_controller.create_linear_keyframe_animation(
                animation_range
            )

            # Create corrective factory
            self.corrective_factory = CorrectiveShapeFactory(
                self.deformation_controller
            )

            # Preview if requested
            if enable_preview:
                self.deformation_controller.test_deformation_preview()

            self._workflow_initialized = True

            # Auto-organize workflow objects after initialization
            self._auto_organize_if_needed()

            pm.displayInfo(
                f"Deformation system initialized: {base_geometry} → {target_geometry} "
                f"({animation_range.start_frame}-{animation_range.end_frame})"
            )
            return True

        except Exception as e:
            pm.error(f"Failed to initialize deformation system: {e}")
            return False

    def create_corrective_shapes(
        self,
        interpolation_mode: InterpolationMode = InterpolationMode.WEIGHT_BASED,
        sample_count: int = 3,
        weight_values: Optional[Sequence[float]] = None,
        frame_positions: Optional[Sequence[int]] = None,
        weight_range: Tuple[float, float] = (0.0, 1.0),
        naming_prefix: str = "corrective",
    ) -> List[CorrectiveShape]:
        """
        Create corrective shapes using specified interpolation method.

        Args:
            interpolation_mode: Weight-based or temporal interpolation
            sample_count: Number of correctives to create (for automatic generation)
            weight_values: Specific weights for correctives
            frame_positions: Specific frames for temporal correctives
            weight_range: Range for automatic weight generation
            naming_prefix: Prefix for corrective geometry names

        Returns:
            List of created corrective shapes
        """
        self._ensure_workflow_ready()

        if interpolation_mode == InterpolationMode.WEIGHT_BASED:
            if weight_values is None:
                weight_values = DeformationMath.generate_weight_distribution(
                    sample_count, *weight_range
                )
            correctives = self.corrective_factory.create_weight_based_correctives(
                weight_values, naming_prefix
            )

        elif interpolation_mode == InterpolationMode.TEMPORAL_BASED:
            if frame_positions is None:
                animation_range = (
                    self.deformation_controller.extract_animation_time_range()
                )
                # Generate frames at 25%, 50%, 75% of animation
                frame_positions = [
                    animation_range.denormalize_weight_to_frame(0.25),
                    animation_range.denormalize_weight_to_frame(0.50),
                    animation_range.denormalize_weight_to_frame(0.75),
                ]
            correctives = self.corrective_factory.create_temporal_correctives(
                frame_positions, naming_prefix
            )

        else:
            raise ValueError(f"Unknown interpolation mode: {interpolation_mode}")

        # Auto-organize the created correctives
        self._auto_organize_if_needed()

        return correctives

    def apply_corrective_modifications(
        self, correctives: Optional[Sequence[CorrectiveShape]] = None
    ) -> List[CorrectiveShape]:
        """
        Apply corrective shape modifications to deformation system.

        Args:
            correctives: Specific correctives to apply, or None for all

        Returns:
            List of successfully applied correctives
        """
        self._ensure_workflow_ready()

        applied_correctives = CorrectiveManager.apply_corrective_modifications(
            self.deformation_controller, correctives
        )

        # Auto-organize after applying modifications
        self._auto_organize_if_needed()

        if applied_correctives:
            pm.displayInfo(
                f"Applied {len(applied_correctives)} corrective modifications"
            )
        else:
            pm.warning("No corrective modifications found to apply")

        return applied_correctives

    def edit_corrective_frame(
        self, target_weight: float, edit_mode: bool = True
    ) -> Optional[CorrectiveShape]:
        """
        Enter edit mode for a specific corrective frame or apply edits.

        Args:
            target_weight: Weight of the corrective to edit (0.0-1.0)
            edit_mode: True to enter edit mode, False to apply edits

        Returns:
            CorrectiveShape being edited or None if not found
        """
        self._ensure_workflow_ready()

        # Find existing corrective at target weight
        existing_correctives = CorrectiveManager.discover_scene_correctives()
        target_corrective = None

        for corrective in existing_correctives:
            if abs(corrective.deformation_weight - target_weight) < 0.001:
                target_corrective = corrective
                break

        if not target_corrective:
            pm.warning(f"No corrective found at weight {target_weight}")
            return None

        if edit_mode:
            # Enter edit mode: set deformation weight and make corrective visible
            self.deformation_controller.set_deformation_weight(target_weight)
            pm.refresh()

            # Make corrective geometry visible and selectable
            if target_corrective.geometry_node.visibility.get() == False:
                target_corrective.geometry_node.visibility.set(True)

            pm.select(target_corrective.geometry_node, replace=True)

            pm.displayInfo(
                f"Editing corrective at weight {target_weight}. "
                f"Edit geometry: {target_corrective.geometry_node}"
            )
            pm.displayInfo(
                "When finished editing, call workflow.apply_corrective_edits() "
                "or workflow.edit_corrective_frame(weight, edit_mode=False)"
            )
        else:
            # Apply edits mode: update the blendShape target
            self._apply_corrective_edits(target_corrective)

        return target_corrective

    def apply_corrective_edits(
        self, target_corrective: Optional[CorrectiveShape] = None
    ) -> bool:
        """
        Apply current corrective geometry edits back to blendShape system.

        Args:
            target_corrective: Specific corrective to update, or None for selected

        Returns:
            True if edits were applied successfully
        """
        self._ensure_workflow_ready()

        if target_corrective is None:
            # Try to find corrective from current selection
            selected = pm.selected()
            if not selected:
                pm.warning(
                    "No corrective selected. Please select a corrective geometry."
                )
                return False

            selected_node = selected[0]
            if not selected_node.hasAttr("isCorrectiveShape"):
                pm.warning(f"{selected_node} is not a corrective shape.")
                return False

            target_corrective = CorrectiveShape(selected_node)

        return self._apply_corrective_edits(target_corrective)

    def _apply_corrective_edits(self, corrective: CorrectiveShape) -> bool:
        """Internal method to apply corrective edits to blendShape system."""
        try:
            # Remove existing intermediate target at this weight
            self._remove_intermediate_target(corrective.deformation_weight)

            # Re-add the corrective with updated geometry
            pm.blendShape(
                self.deformation_controller.blendshape_node,
                edit=True,
                inBetween=True,
                target=(
                    self.deformation_controller.base_geometry,
                    self.deformation_controller.target_index,
                    corrective.geometry_node,
                    corrective.deformation_weight,
                ),
            )

            pm.displayInfo(
                f"Applied edits for corrective at weight {corrective.deformation_weight}"
            )
            return True

        except Exception as e:
            pm.error(f"Failed to apply corrective edits: {e}")
            return False

    def _remove_intermediate_target(self, weight: float) -> None:
        """Remove intermediate blendShape target at specific weight."""
        try:
            # Query existing intermediate targets
            intermediate_info = (
                pm.blendShape(
                    self.deformation_controller.blendshape_node,
                    query=True,
                    inBetween=True,
                    target=self.deformation_controller.target_index,
                )
                or []
            )

            # Find and remove target at specified weight
            for i in range(0, len(intermediate_info), 2):
                if i + 1 < len(intermediate_info):
                    target_weight = intermediate_info[i + 1]
                    if abs(target_weight - weight) < 0.001:
                        pm.blendShape(
                            self.deformation_controller.blendshape_node,
                            edit=True,
                            remove=True,
                            inBetween=True,
                            target=(
                                self.deformation_controller.base_geometry,
                                self.deformation_controller.target_index,
                                weight,
                            ),
                        )
                        break
        except Exception:
            pass  # Target might not exist, which is okay

    def list_corrective_frames(self) -> List[Dict]:
        """
        List all available corrective frames with their information.

        Returns:
            List of dictionaries containing corrective frame information
        """
        self._ensure_workflow_ready()

        correctives = CorrectiveManager.discover_scene_correctives()
        frame_info = []

        for corrective in correctives:
            info = {
                "weight": corrective.deformation_weight,
                "geometry": str(corrective.geometry_node),
                "frame": corrective.creation_frame,
                "visible": corrective.geometry_node.visibility.get(),
            }
            frame_info.append(info)

        # Sort by weight
        frame_info.sort(key=lambda x: x["weight"])

        pm.displayInfo(f"Found {len(frame_info)} corrective frames:")
        for info in frame_info:
            frame_str = f" (frame {info['frame']})" if info["frame"] else ""
            pm.displayInfo(f"  Weight {info['weight']}: {info['geometry']}{frame_str}")

        return frame_info

    def finalize_workflow(
        self,
        archive_correctives: bool = True,
        cleanup_organization: bool = True,
        cleanup_temporary: bool = True,
    ) -> None:
        """
        Finalize workflow with comprehensive cleanup operations.
        Organization happens automatically throughout the workflow.

        Args:
            archive_correctives: Whether to archive corrective shapes
            cleanup_organization: Whether to clean up empty groups
            cleanup_temporary: Whether to clean up temporary objects
        """
        self._ensure_workflow_ready()

        # Final organization pass (automatic)
        self._auto_organize_if_needed()

        if archive_correctives:
            correctives = CorrectiveManager.discover_scene_correctives()
            for corrective in correctives:
                AssetOrganizer.archive_geometry_node(corrective.geometry_node)
            pm.displayInfo(f"Archived {len(correctives)} corrective shapes")

        if cleanup_temporary:
            cleaned_count = AssetOrganizer.cleanup_temporary_objects()
            if cleaned_count > 0:
                pm.displayInfo(f"Cleaned up {cleaned_count} temporary objects")

        if cleanup_organization:
            removed_count = AssetOrganizer.cleanup_empty_organization()
            if removed_count:
                pm.displayInfo(f"Cleaned up {removed_count} empty groups")

        # Show final organization summary
        pm.displayInfo("\n=== Final Organization Summary ===")
        org_summary = AssetOrganizer.get_organization_summary()
        for category, count in org_summary.items():
            if count > 0:
                pm.displayInfo(f"{category.title()}: {count} objects")

        pm.displayInfo("Workflow finalization complete!")

    def cleanup_workflow_objects(self) -> None:
        """Clean up all objects created by this workflow. Organization is automatic."""
        self._ensure_workflow_ready()

        # Archive correctives
        correctives = CorrectiveManager.discover_scene_correctives()
        for corrective in correctives:
            AssetOrganizer.archive_geometry_node(corrective.geometry_node)

        # Clean temporary objects
        AssetOrganizer.cleanup_temporary_objects()

        pm.displayInfo(
            f"Cleaned up workflow objects: {len(correctives)} correctives archived"
        )

    def organize_workflow_objects(self) -> None:
        """
        Manually organize all workflow objects into proper groups.
        Note: Organization now happens automatically in most operations.
        """
        self._auto_organize_if_needed()
        pm.displayInfo("Manual organization completed")

    # ===========================================================================
    # Workflow Recovery and Loading
    # ===========================================================================

    @classmethod
    def get_workflow(
        cls, base_geometry: Optional[pm.PyNode] = None
    ) -> BlendShapeDeformationWorkflow:
        """
        Retrieve an existing workflow from a base mesh with blendShape deformation.

        Args:
            base_geometry: Mesh with existing blendShape, or None to use selection

        Returns:
            Configured workflow instance

        Raises:
            ValueError: If no valid blendShape system is found
            RuntimeError: If workflow configuration fails
        """
        if base_geometry is None:
            selection = pm.selected()
            if not selection:
                raise ValueError(
                    "Please select base geometry or provide base_geometry parameter"
                )
            base_geometry = selection[0]

        try:
            # Validate base geometry
            base_geometry = GeometryValidator.validate_mesh_transform(base_geometry)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid base geometry: {e}")

        # Locate blendShape deformer
        deformation_history = base_geometry.listHistory(type="blendShape")
        if not deformation_history:
            raise ValueError(f"No blendShape deformer found on {base_geometry}")

        blendshape_node = deformation_history[0]

        # Locate target geometry from blendShape targets
        target_geometries = (
            pm.blendShape(blendshape_node, query=True, target=True) or []
        )
        if not target_geometries:
            raise ValueError(f"No target geometries found in {blendshape_node}")

        target_geometry = pm.PyNode(target_geometries[0])

        # Validate target geometry exists and is accessible
        if not pm.objExists(target_geometry):
            raise ValueError(f"Target geometry {target_geometry} no longer exists")

        try:
            target_geometry = GeometryValidator.validate_mesh_transform(target_geometry)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid target geometry: {e}")

        # Create and configure workflow instance
        workflow = cls()
        try:
            workflow.deformation_controller = DeformationController(
                base_geometry, target_geometry, blendshape_node
            )
            workflow.corrective_factory = CorrectiveShapeFactory(
                workflow.deformation_controller
            )
            workflow._workflow_initialized = True

            # Discover existing correctives
            existing_correctives = CorrectiveManager.discover_scene_correctives()
            corrective_count = len(existing_correctives)

            pm.displayInfo(
                f"Retrieved workflow: {base_geometry} → {target_geometry} "
                f"({corrective_count} correctives found)"
            )
            return workflow

        except Exception as e:
            raise RuntimeError(
                f"Failed to configure workflow from existing system: {e}"
            )

    @classmethod
    def load_existing_deformation_system(
        cls, base_geometry: Optional[pm.PyNode] = None
    ) -> BlendShapeDeformationWorkflow:
        """
        Load existing deformation system for additional editing.

        Args:
            base_geometry: Mesh with existing blendShape, or None for selection

        Returns:
            Configured workflow

        Raises:
            ValueError: If no valid blendShape system is found
        """
        if base_geometry is None:
            selection = pm.selected()
            if not selection:
                raise ValueError(
                    "Please select base geometry or provide base_geometry parameter"
                )
            base_geometry = selection[0]

        # Locate blendShape deformer
        deformation_history = base_geometry.listHistory(type="blendShape")
        if not deformation_history:
            raise ValueError(f"No blendShape deformer found on {base_geometry}")

        blendshape_node = deformation_history[0]

        # Locate target geometry
        target_geometries = (
            pm.blendShape(blendshape_node, query=True, target=True) or []
        )
        if not target_geometries:
            raise ValueError(f"No target geometries found in {blendshape_node}")

        target_geometry = pm.PyNode(target_geometries[0])

        # Configure workflow
        workflow = cls()
        workflow.deformation_controller = DeformationController(
            base_geometry, target_geometry, blendshape_node
        )
        workflow.corrective_factory = CorrectiveShapeFactory(
            workflow.deformation_controller
        )
        workflow._workflow_initialized = True

        pm.displayInfo(
            f"Loaded existing deformation system: {base_geometry} → {target_geometry}"
        )
        return workflow

    @classmethod
    def recover_corrupted_deformation_system(
        cls,
        base_geometry: Optional[pm.PyNode] = None,
        target_geometry: Optional[pm.PyNode] = None,
    ) -> BlendShapeDeformationWorkflow:
        """
        Recover corrupted deformation system while preserving correctives.

        Args:
            base_geometry: Base mesh of corrupted system
            target_geometry: Target mesh of corrupted system

        Returns:
            Recovered workflow

        Raises:
            ValueError: If recovery parameters are invalid
            RuntimeError: If recovery process fails
        """
        if base_geometry is None or target_geometry is None:
            selection = pm.selected()
            if len(selection) != 2:
                raise ValueError("Please select 2 meshes or provide both parameters")
            base_geometry, target_geometry = selection

        try:
            # Preserve existing keyframe data and correctives
            deformation_history = base_geometry.listHistory(type="blendShape")
            keyframe_data = []
            if deformation_history:
                old_blendshape = deformation_history[0]
                try:
                    keyframe_times = (
                        pm.keyframe(
                            f"{old_blendshape}.weight[0]", query=True, timeChange=True
                        )
                        or []
                    )
                    keyframe_values = (
                        pm.keyframe(
                            f"{old_blendshape}.weight[0]", query=True, valueChange=True
                        )
                        or []
                    )
                    keyframe_data = list(zip(keyframe_times, keyframe_values))
                except:
                    pass
                pm.delete(old_blendshape)

            existing_correctives = CorrectiveManager.discover_scene_correctives()

            # Create fresh deformation system
            animation_range = (
                TimeRange(int(keyframe_data[0][0]), int(keyframe_data[-1][0]))
                if keyframe_data
                else TimeRange(5500, 5800)
            )

            workflow = cls()
            success = workflow.initialize_deformation_system(
                base_geometry,
                target_geometry,
                animation_range,
                system_name=f"{base_geometry}_recovered",
                enable_preview=False,
            )

            if not success:
                raise RuntimeError("Failed to initialize recovered deformation system")

            # Restore keyframe animation
            if keyframe_data:
                pm.cutKey(
                    workflow.deformation_controller.blendshape_node,
                    attribute="weight[0]",
                    clear=True,
                )
                for time, value in keyframe_data:
                    pm.setKeyframe(
                        workflow.deformation_controller.blendshape_node,
                        attribute="weight[0]",
                        time=time,
                        value=value,
                    )

            # Update and apply existing correctives
            if existing_correctives:
                CorrectiveManager.update_corrective_references(
                    workflow.deformation_controller.blendshape_node,
                    workflow.deformation_controller.base_geometry,
                )
                workflow.apply_corrective_modifications(existing_correctives)

            pm.displayInfo(
                f"Recovery complete: {len(existing_correctives)} correctives restored"
            )
            return workflow

        except Exception as e:
            raise RuntimeError(f"Recovery failed: {e}")

    # ===========================================================================
    # Workflow Utilities and Information
    # ===========================================================================

    def get_workflow_information(self) -> Dict:
        """Get comprehensive information about current workflow state."""
        self._ensure_workflow_ready()

        animation_range = self.deformation_controller.extract_animation_time_range()
        correctives = CorrectiveManager.discover_scene_correctives()
        weight_groups = CorrectiveManager.group_correctives_by_weight(correctives)

        return {
            "base_geometry": str(self.deformation_controller.base_geometry),
            "target_geometry": str(self.deformation_controller.target_geometry),
            "blendshape_node": str(self.deformation_controller.blendshape_node),
            "animation_range": (animation_range.start_frame, animation_range.end_frame),
            "current_weight": self.deformation_controller.get_current_weight(),
            "corrective_count": len(correctives),
            "weight_distribution": {
                w: len(group) for w, group in weight_groups.items()
            },
            "workflow_initialized": self._workflow_initialized,
        }

    def preview_deformation_sequence(self, preview_steps: int = 10) -> None:
        """Preview deformation by stepping through weight sequence."""
        self._ensure_workflow_ready()

        original_weight = self.deformation_controller.get_current_weight()
        preview_weights = DeformationMath.generate_weight_distribution(
            preview_steps, include_bounds=True
        )

        try:
            for weight in preview_weights:
                self.deformation_controller.set_deformation_weight(weight)
                pm.refresh()
                pm.pause(sec=0.2)  # Brief pause for visual feedback
        finally:
            self.deformation_controller.set_deformation_weight(original_weight)

    def _ensure_workflow_ready(self) -> None:
        """Ensure workflow is properly initialized before operations. Auto-initializes if needed."""
        if (
            not self._workflow_initialized
            or not self.deformation_controller
            or not self.corrective_factory
        ):
            # Try to auto-initialize workflow from selection or scene
            try:
                pm.displayInfo("Auto-initializing workflow...")
                workflow = self.__class__.get_or_create_workflow()

                # Copy the initialized state to this instance
                self.deformation_controller = workflow.deformation_controller
                self.corrective_factory = workflow.corrective_factory
                self._workflow_initialized = workflow._workflow_initialized

                # Auto-organize objects
                self._auto_organize_if_needed()

            except Exception as e:
                raise RuntimeError(
                    f"Workflow not initialized and auto-initialization failed: {e}\n"
                    "Please select base geometry or call initialize_deformation_system() manually."
                )

    def _auto_organize_if_needed(self) -> None:
        """Automatically organize workflow objects if workflow is ready."""
        if self._workflow_initialized:
            try:
                AssetOrganizer.organize_all_workflow_objects(self)
            except Exception:
                pass  # Organization is not critical - don't fail the workflow

    # ===========================================================================
    # STREAMLINED WORKFLOW METHODS
    # ===========================================================================

    @classmethod
    def get_workflow_auto(cls) -> BlendShapeDeformationWorkflow:
        """
        Streamlined entry point - automatically handles everything.
        Just select geometry and call this method.

        Returns:
            Ready-to-use workflow with automatic organization
        """
        try:
            workflow = cls.get_or_create_workflow()
            # Organization is handled automatically in _ensure_workflow_ready
            return workflow
        except Exception as e:
            pm.error(f"Auto-workflow failed: {e}")
            raise

    # ===========================================================================
    # USER-FRIENDLY WORKFLOW METHODS
    # ===========================================================================

    @classmethod
    def get_or_create_workflow(cls) -> BlendShapeDeformationWorkflow:
        """
        Get an existing workflow or create a new one automatically.
        This is the main entry point for users.

        Returns:
            Ready-to-use workflow instance
        """
        try:
            # Try to get existing workflow
            return cls.get_workflow()
        except ValueError as e:
            if "No target geometries found" in str(e):
                # Corrupted system - check for existing correctives before repair
                existing_correctives = CorrectiveManager.discover_scene_correctives()
                if existing_correctives:
                    pm.warning(
                        f"Found corrupted blendShape system with {len(existing_correctives)} correctives. Using restoration workflow..."
                    )
                    return cls.restore_editable_morph_system()
                else:
                    # No correctives, use standard repair
                    pm.warning(
                        "Found corrupted blendShape system. Attempting automatic repair..."
                    )
                    return cls._auto_repair_corrupted_system()
            elif "No blendShape deformer found" in str(e):
                # No blendShape at all - check for previous animation data
                pm.warning("No blendShape system found on selected mesh.")

                # Check if there might be animation data we should preserve
                selection = pm.selected()
                if selection:
                    base_geometry = selection[0]

                    # Check if user selected a target mesh instead of base mesh
                    if cls._is_likely_target_mesh(base_geometry):
                        pm.warning(
                            "It looks like you selected a target mesh instead of the base mesh."
                        )
                        original_base = cls._find_original_base_mesh(base_geometry)
                        if original_base:
                            pm.displayInfo(
                                f"Found likely original base mesh: {original_base}"
                            )
                            pm.displayInfo(
                                "Attempting to recover workflow from original base..."
                            )
                            try:
                                # Try to get workflow from the original base
                                pm.select(original_base, replace=True)
                                return cls.get_workflow()
                            except ValueError:
                                # Original base also has issues, proceed with recovery
                                pm.warning(
                                    "Original base mesh also has issues. Proceeding with recovery..."
                                )
                                base_geometry = original_base

                    existing_animation = cls._check_for_existing_animation(
                        base_geometry
                    )
                    if existing_animation:
                        pm.warning(
                            "Found existing animation data! Attempting to preserve it..."
                        )
                        return cls._create_system_with_preserved_animation(
                            base_geometry, existing_animation
                        )

                return cls._guide_new_system_creation()
            else:
                # Other issues - provide clear guidance
                raise RuntimeError(f"Cannot create workflow: {e}")

    @classmethod
    def _check_for_existing_animation(cls, geometry_node: pm.PyNode) -> Optional[Dict]:
        """Check for existing animation data on a geometry node."""
        animation_data = {"keyframes": [], "time_range": None, "has_animation": False}

        try:
            # Check for keyframes on common attributes
            attrs_to_check = []

            # Get all attributes on the node
            all_attrs = pm.listAttr(geometry_node, keyable=True) or []

            # Look for blendShape-related or weight-related attributes
            for attr in all_attrs:
                attr_name = str(attr).lower()
                if any(
                    keyword in attr_name
                    for keyword in ["weight", "blend", "morph", "deform"]
                ):
                    full_attr = f"{geometry_node}.{attr}"
                    attrs_to_check.append(full_attr)

            # Also check connected nodes for animation
            connections = (
                pm.listConnections(geometry_node, source=True, type="animCurve") or []
            )

            for connection in connections:
                try:
                    keyframe_times = (
                        pm.keyframe(connection, query=True, timeChange=True) or []
                    )
                    keyframe_values = (
                        pm.keyframe(connection, query=True, valueChange=True) or []
                    )

                    if keyframe_times and keyframe_values:
                        animation_data["keyframes"].extend(
                            list(zip(keyframe_times, keyframe_values))
                        )
                        animation_data["has_animation"] = True

                        if not animation_data["time_range"]:
                            animation_data["time_range"] = [
                                min(keyframe_times),
                                max(keyframe_times),
                            ]
                        else:
                            animation_data["time_range"][0] = min(
                                animation_data["time_range"][0], min(keyframe_times)
                            )
                            animation_data["time_range"][1] = max(
                                animation_data["time_range"][1], max(keyframe_times)
                            )

                except Exception:
                    continue

            return animation_data if animation_data["has_animation"] else None

        except Exception:
            return None

    @classmethod
    def _create_system_with_preserved_animation(
        cls, base_geometry: pm.PyNode, animation_data: Dict
    ) -> BlendShapeDeformationWorkflow:
        """Create a new system while preserving existing animation data."""
        try:
            pm.displayInfo("Creating new system with preserved animation...")

            # Create the new system first
            workflow = cls._guide_new_system_creation()

            # Apply preserved animation data if we have a valid time range
            if (
                animation_data.get("time_range")
                and len(animation_data["time_range"]) == 2
            ):
                start_frame, end_frame = animation_data["time_range"]
                pm.displayInfo(
                    f"Preserving animation range: {start_frame} - {end_frame}"
                )

                # Update the controller with preserved time range
                if workflow.deformation_controller:
                    preserved_range = TimeRange(int(start_frame), int(end_frame))
                    workflow.deformation_controller.create_linear_keyframe_animation(
                        preserved_range
                    )
                    pm.displayInfo("Animation range preserved!")

            # If we have specific keyframes, try to apply them
            if animation_data.get("keyframes"):
                pm.displayInfo(
                    f"Attempting to restore {len(animation_data['keyframes'])} keyframes..."
                )
                # This is a best-effort attempt - may not work perfectly depending on the original setup

            pm.displayInfo("System created with preserved animation data!")
            return workflow

        except Exception as e:
            pm.warning(f"Failed to preserve animation data: {e}")
            pm.displayInfo("Creating standard new system...")
            return cls._guide_new_system_creation()

    @classmethod
    def _is_likely_target_mesh(cls, mesh: pm.PyNode) -> bool:
        """Check if a mesh is likely a target mesh based on naming patterns."""
        mesh_name = str(mesh).lower()
        target_indicators = [
            "_target",
            "_morph",
            "_blend",
            "_deform",
            "target_",
            "morph_",
        ]
        return any(indicator in mesh_name for indicator in target_indicators)

    @classmethod
    def _find_original_base_mesh(cls, target_mesh: pm.PyNode) -> Optional[pm.PyNode]:
        """Try to find the original base mesh from a target mesh."""
        mesh_name = str(target_mesh)

        # Try removing common target suffixes
        possible_base_names = []

        # Remove target suffixes
        for suffix in ["_target", "_morph", "_blend", "_deform"]:
            if suffix in mesh_name:
                possible_base_names.append(mesh_name.replace(suffix, ""))

        # Try removing target prefixes
        for prefix in ["target_", "morph_"]:
            if mesh_name.startswith(prefix):
                possible_base_names.append(mesh_name[len(prefix) :])

        # Also try the full path variants
        if "|" in mesh_name:
            parts = mesh_name.split("|")
            for i, part in enumerate(parts):
                for suffix in ["_target", "_morph", "_blend", "_deform"]:
                    if suffix in part:
                        new_part = part.replace(suffix, "")
                        new_parts = parts.copy()
                        new_parts[i] = new_part
                        possible_base_names.append("|".join(new_parts))

        # Check if any of these possible names exist
        for name in possible_base_names:
            if pm.objExists(name):
                try:
                    base_node = pm.PyNode(name)
                    # Verify it's a valid mesh
                    GeometryValidator.validate_mesh_transform(base_node)
                    return base_node
                except:
                    continue

        return None

    @classmethod
    def _auto_repair_corrupted_system(cls) -> BlendShapeDeformationWorkflow:
        """Automatically repair a corrupted blendShape system, preserving work via resampling."""
        try:
            selection = pm.selected()
            if not selection:
                raise RuntimeError(
                    "Please select the mesh with the corrupted blendShape"
                )

            base_geometry = selection[0]

            # Check if we can resample before repair
            resampled_correctives = []
            existing_correctives = CorrectiveManager.discover_scene_correctives()

            if existing_correctives:
                pm.displayInfo(
                    f"Found {len(existing_correctives)} existing correctives to preserve"
                )
                resampled_correctives = (
                    existing_correctives  # Use existing correctives directly
                )
            else:
                # Try to resample only if we have a working blendShape with keyframes
                blendshape_history = base_geometry.listHistory(type="blendShape")
                if blendshape_history:
                    try:
                        blendshape_node = blendshape_history[0]
                        # Check if blendShape has any targets before attempting resample
                        targets = (
                            pm.blendShape(blendshape_node, query=True, target=True)
                            or []
                        )

                        if targets and len(targets) > 0:
                            # Only try resampling if we have valid targets
                            temp_workflow = cls()
                            temp_workflow.deformation_controller = (
                                DeformationController(
                                    base_geometry,
                                    pm.PyNode(targets[0]),  # Use first valid target
                                    blendshape_node,
                                )
                            )
                            temp_workflow._workflow_initialized = True

                            pm.displayInfo(
                                "Attempting to preserve existing work via resampling..."
                            )
                            resampled_correctives = temp_workflow.resample_animation(
                                resolution=8, preserve_existing=True, cleanup_temp=False
                            )
                            pm.displayInfo(
                                f"Preserved {len(resampled_correctives)} animation samples"
                            )
                        else:
                            pm.displayInfo("No valid targets found - skipping resample")

                    except Exception as resample_error:
                        pm.warning(
                            f"Could not resample existing work: {resample_error}"
                        )
                        pm.displayInfo("Proceeding with standard repair...")

            # Delete the corrupted blendShape and create a fresh one
            pm.displayInfo("Repairing corrupted system...")

            # Clean up the name for Maya deformer naming (remove pipes and invalid chars)
            base_name = str(base_geometry).split("|")[-1]  # Get just the object name
            clean_name = base_name.replace("|", "_").replace(":", "_").replace(" ", "_")

            # Create a duplicate to use as target for now
            target_name = f"{clean_name}_target"
            target_geometry = pm.duplicate(base_geometry, name=target_name)[0]

            # Remove any existing blendShape
            history = base_geometry.listHistory(type="blendShape")
            if history:
                pm.delete(history[0])

            # Create new workflow with clean system name
            workflow = cls()
            system_name = f"{clean_name}_repaired"
            success = workflow.initialize_deformation_system(
                base_geometry, target_geometry, system_name=system_name
            )

            if success:
                # Apply resampled correctives if we have them
                if resampled_correctives:
                    pm.displayInfo("Applying preserved animation samples...")
                    try:
                        # Update corrective references to new system
                        updated_correctives = (
                            CorrectiveManager.update_corrective_references(
                                workflow.deformation_controller.blendshape_node,
                                workflow.deformation_controller.base_geometry,
                            )
                        )

                        # Apply the preserved correctives
                        applied_correctives = workflow.apply_corrective_modifications(
                            updated_correctives
                        )
                        pm.displayInfo(
                            f"Restored {len(applied_correctives)} preserved animation samples"
                        )

                    except Exception as apply_error:
                        pm.warning(f"Could not apply preserved samples: {apply_error}")

                pm.displayInfo("System repaired! You can now edit correctives.")
                pm.displayInfo(f"Note: Created temporary target '{target_geometry}'")
                if resampled_correctives:
                    pm.displayInfo(
                        "Previous animation work has been preserved and applied."
                    )
                pm.displayInfo("Replace with your actual morph target when ready.")
                return workflow
            else:
                raise RuntimeError("Failed to repair system")

        except Exception as e:
            raise RuntimeError(f"Auto-repair failed: {e}")

    @classmethod
    def _guide_new_system_creation(cls) -> BlendShapeDeformationWorkflow:
        """Guide user through creating a new system."""
        selection = pm.selected()

        if len(selection) == 2:
            # User has base and target selected
            pm.displayInfo("Creating new blendShape system from selection...")
            workflow = cls()
            success = workflow.initialize_deformation_system()
            if success:
                pm.displayInfo("New blendShape system created successfully!")
                return workflow
            else:
                raise RuntimeError("Failed to create new system")

        elif len(selection) == 1:
            # Only base selected - create target automatically
            pm.displayInfo("Creating new blendShape system with automatic target...")
            base_geometry = selection[0]

            # Clean up the name for Maya deformer naming
            base_name = str(base_geometry).split("|")[-1]  # Get just the object name
            clean_name = base_name.replace("|", "_").replace(":", "_").replace(" ", "_")

            target_name = f"{clean_name}_morph"
            target_geometry = pm.duplicate(base_geometry, name=target_name)[0]

            # Organization is now automatic

            workflow = cls()
            success = workflow.initialize_deformation_system(
                base_geometry, target_geometry
            )
            if success:
                # Organization is now automatic in initialize_deformation_system
                pm.displayInfo(f"New blendShape system created!")
                pm.displayInfo(f"Edit '{target_geometry}' to create your morph target.")
                return workflow
            else:
                raise RuntimeError("Failed to create new system")
        else:
            raise RuntimeError(
                "Please select:\n"
                "  - 1 mesh (will create automatic target), or\n"
                "  - 2 meshes (base and target)"
            )

    @classmethod
    def create_new(
        cls, base_geometry=None, target_geometry=None
    ) -> BlendShapeDeformationWorkflow:
        """
        Create a completely new workflow system.

        Args:
            base_geometry: Base mesh, or None to use selection
            target_geometry: Target mesh, or None to create automatically

        Returns:
            New workflow ready for use
        """
        workflow = cls()

        if base_geometry is None or target_geometry is None:
            selection = pm.selected()
            if len(selection) >= 1:
                base_geometry = selection[0]
                if len(selection) >= 2:
                    target_geometry = selection[1]
                else:
                    # Create automatic target with clean name
                    base_name = str(base_geometry).split("|")[
                        -1
                    ]  # Get just the object name
                    clean_name = (
                        base_name.replace("|", "_").replace(":", "_").replace(" ", "_")
                    )
                    target_name = f"{clean_name}_target"
                    target_geometry = pm.duplicate(base_geometry, name=target_name)[0]

                    # Organization is now automatic
            else:
                raise ValueError("Please select base geometry or provide parameters")

        success = workflow.initialize_deformation_system(base_geometry, target_geometry)
        if not success:
            raise RuntimeError("Failed to create new workflow")

        # Organization is now automatic in initialize_deformation_system
        pm.displayInfo("New workflow created and ready!")
        return workflow

    @classmethod
    def quick_setup(cls, corrective_count: int = 3) -> BlendShapeDeformationWorkflow:
        """
        Quick setup: create new system and correctives in one step.

        Args:
            corrective_count: Number of corrective shapes to create

        Returns:
            Workflow with correctives ready for editing
        """
        workflow = cls.create_new()
        correctives = workflow.create_corrective_shapes(count=corrective_count)

        pm.displayInfo(f"Quick setup complete! Created {len(correctives)} correctives.")
        pm.displayInfo(
            "Edit the corrective shapes, then run workflow.apply_corrective_edits()"
        )
        return workflow

    def show_status(self) -> None:
        """Show current workflow status in a user-friendly way."""
        if not self._workflow_initialized:
            pm.displayInfo("Workflow Status: NOT INITIALIZED")
            pm.displayInfo("Use workflow.initialize_deformation_system() first")
            return

        info = self.get_workflow_information()

        pm.displayInfo("=== Workflow Status ===")
        pm.displayInfo(f"Base Mesh: {info['base_geometry']}")
        pm.displayInfo(f"Target Mesh: {info['target_geometry']}")
        pm.displayInfo(f"BlendShape: {info['blendshape_node']}")
        pm.displayInfo(
            f"Animation: frames {info['animation_range'][0]}-{info['animation_range'][1]}"
        )
        pm.displayInfo(f"Current Weight: {info['current_weight']:.3f}")
        pm.displayInfo(f"Correctives: {info['corrective_count']} found")

        if info["corrective_count"] > 0:
            pm.displayInfo("Weight distribution:")
            for weight, count in info["weight_distribution"].items():
                pm.displayInfo(f"  {weight:.3f}: {count} corrective(s)")

        # Show organization status
        pm.displayInfo("\n=== Organization Status ===")
        org_summary = AssetOrganizer.get_organization_summary()
        for category, count in org_summary.items():
            if count > 0:
                pm.displayInfo(f"{category.title()}: {count} objects")

        if sum(org_summary.values()) == 0:
            pm.displayInfo("No organized objects found")
        else:
            pm.displayInfo(f"Total organized objects: {sum(org_summary.values())}")

    def create_corrective_shapes(
        self, count: int = 3, weights: List[float] = None
    ) -> List[CorrectiveShape]:
        """
        Create corrective shapes with simple parameters.

        Args:
            count: Number of correctives to create (ignored if weights provided)
            weights: Specific weight values, or None for automatic distribution

        Returns:
            List of created corrective shapes
        """
        self._ensure_workflow_ready()

        if weights is None:
            # Create evenly distributed weights
            if count <= 1:
                weights = [0.5]
            else:
                step = 1.0 / (count + 1)
                weights = [step * (i + 1) for i in range(count)]

        return self.corrective_factory.create_weight_based_correctives(
            weights, "corrective"
        )

    def edit_corrective_frame(self, weight: float) -> Optional[CorrectiveShape]:
        """
        Edit a corrective frame - simplified interface.

        Args:
            weight: Weight of corrective to edit (0.0-1.0)

        Returns:
            CorrectiveShape being edited
        """
        return super().edit_corrective_frame(weight, edit_mode=True)

    def update_animation_range(self, start_frame: int, end_frame: int) -> None:
        """
        Update the animation range for the workflow.
        Useful when recovering lost animation data.

        Args:
            start_frame: Starting frame of animation
            end_frame: Ending frame of animation
        """
        self._ensure_workflow_ready()

        new_range = TimeRange(start_frame, end_frame)
        self.deformation_controller.create_linear_keyframe_animation(new_range)

        pm.displayInfo(f"Animation range updated to: {start_frame} - {end_frame}")

    def restore_animation_from_range(self, start_frame: int, end_frame: int) -> None:
        """
        Restore animation using known frame range.
        Use this if you know your previous animation's frame range.

        Args:
            start_frame: Starting frame of your previous animation
            end_frame: Ending frame of your previous animation
        """
        pm.displayInfo(f"Restoring animation for range: {start_frame} - {end_frame}")
        self.update_animation_range(start_frame, end_frame)
        pm.displayInfo("Animation restored! Your previous frame range is now active.")

    def resample_animation(
        self,
        resolution: int = 10,
        preserve_existing: bool = True,
        cleanup_temp: bool = True,
        start_frame: Optional[int] = None,
        end_frame: Optional[int] = None,
    ) -> List[CorrectiveShape]:
        """
        Resample the current animation to create evenly spaced tween targets.
        Useful for preserving work when creating new systems or smoothing animations.

        Args:
            resolution: Number of sample points to create
            preserve_existing: Whether to preserve existing corrective shapes
            cleanup_temp: Whether to clean up temporary objects after sampling
            start_frame: Custom start frame, or None to use current animation range
            end_frame: Custom end frame, or None to use current animation range

        Returns:
            List of created corrective shapes
        """
        self._ensure_workflow_ready()

        # Get current animation range
        if start_frame is None or end_frame is None:
            current_range = self.deformation_controller.extract_animation_time_range()
            start_frame = start_frame or current_range.start_frame
            end_frame = end_frame or current_range.end_frame

        sample_range = TimeRange(start_frame, end_frame)

        pm.displayInfo(
            f"Resampling animation with {resolution} samples over frames {start_frame}-{end_frame}"
        )

        # Store current state
        original_frame = pm.currentTime(query=True)
        original_weight = self.deformation_controller.get_current_weight()

        # Preserve existing correctives if requested
        existing_correctives = []
        if preserve_existing:
            existing_correctives = CorrectiveManager.discover_scene_correctives()
            pm.displayInfo(
                f"Preserving {len(existing_correctives)} existing correctives"
            )

        # Generate sample weights (evenly distributed, excluding 0.0 and 1.0)
        if resolution <= 1:
            sample_weights = [0.5]
        else:
            step = 1.0 / (resolution + 1)
            sample_weights = [step * (i + 1) for i in range(resolution)]

        created_correctives = []

        try:
            # Sample the animation at each weight point
            for i, weight in enumerate(sample_weights):
                # Set the deformation weight to sample at this point
                self.deformation_controller.set_deformation_weight(weight)

                # Sample at the corresponding frame for temporal information
                sample_frame = sample_range.denormalize_weight_to_frame(weight)
                pm.currentTime(sample_frame)
                pm.refresh()

                # Create a corrective shape at this weight
                pm.displayInfo(
                    f"Sampling at weight {weight:.3f} (frame {sample_frame})"
                )

                # Get the current deformed state of the base geometry
                base_mesh = self.deformation_controller.base_geometry

                # Create a snapshot of the current deformed state
                sample_name = f"resample_{weight:.3f}".replace(".", "_")
                sample_geometry = pm.duplicate(base_mesh, name=sample_name)[0]

                # Create corrective shape object
                corrective = CorrectiveShape(sample_geometry, weight, sample_frame)
                corrective.geometry_node.addAttr(
                    "isCorrectiveShape", attributeType="bool", defaultValue=True
                )
                corrective.geometry_node.addAttr(
                    "deformationWeight", attributeType="float", defaultValue=weight
                )
                corrective.geometry_node.addAttr(
                    "creationFrame", attributeType="long", defaultValue=sample_frame
                )

                created_correctives.append(corrective)

            # Auto-organize the created samples
            self._auto_organize_if_needed()

            pm.displayInfo(f"Created {len(created_correctives)} resampled correctives")

            # Optionally clean up temporary objects
            if cleanup_temp:
                temp_cleaned = AssetOrganizer.cleanup_temporary_objects()
                if temp_cleaned > 0:
                    pm.displayInfo(f"Cleaned up {temp_cleaned} temporary objects")

            return created_correctives

        except Exception as e:
            pm.error(f"Animation resampling failed: {e}")
            return []

        finally:
            # Restore original state
            try:
                self.deformation_controller.set_deformation_weight(original_weight)
                pm.currentTime(original_frame)
            except:
                pass

    def resample_and_rebuild(
        self, resolution: int = 10, new_system_name: Optional[str] = None
    ) -> BlendShapeDeformationWorkflow:
        """
        Resample current animation and rebuild a clean system with the samples.
        Useful for recovering work when the blendShape system is corrupted.

        Args:
            resolution: Number of sample points to preserve
            new_system_name: Name for the rebuilt system, or None for auto-generated

        Returns:
            New workflow with resampled data
        """
        self._ensure_workflow_ready()

        pm.displayInfo("Resampling current animation before rebuilding...")

        # Resample the current animation
        resampled_correctives = self.resample_animation(
            resolution=resolution, preserve_existing=True, cleanup_temp=False
        )

        if not resampled_correctives:
            raise RuntimeError("Failed to resample animation - no correctives created")

        # Get current system information
        base_geometry = self.deformation_controller.base_geometry
        target_geometry = self.deformation_controller.target_geometry
        current_range = self.deformation_controller.extract_animation_time_range()

        # Generate clean system name
        if new_system_name is None:
            base_name = str(base_geometry).split("|")[-1]
            clean_name = base_name.replace("|", "_").replace(":", "_").replace(" ", "_")
            new_system_name = f"{clean_name}_resampled"

        # Archive the old system
        pm.displayInfo("Archiving old system...")
        old_blendshape = self.deformation_controller.blendshape_node
        AssetOrganizer.archive_geometry_node(old_blendshape)

        # Create new clean system
        pm.displayInfo("Creating new clean system...")
        new_workflow = self.__class__()
        success = new_workflow.initialize_deformation_system(
            base_geometry,
            target_geometry,
            animation_range=(current_range.start_frame, current_range.end_frame),
            system_name=new_system_name,
        )

        if not success:
            raise RuntimeError("Failed to create new system during rebuild")

        # Apply the resampled correctives to the new system
        pm.displayInfo("Applying resampled correctives to new system...")

        # Update corrective references to point to new system
        updated_correctives = CorrectiveManager.update_corrective_references(
            new_workflow.deformation_controller.blendshape_node,
            new_workflow.deformation_controller.base_geometry,
        )

        # Apply the correctives
        applied_correctives = new_workflow.apply_corrective_modifications(
            updated_correctives
        )

        pm.displayInfo(
            f"Rebuild complete! Applied {len(applied_correctives)} resampled correctives"
        )
        pm.displayInfo(f"New system: {new_system_name}")

        return new_workflow

    @classmethod
    def find_and_recover_workflow(cls) -> BlendShapeDeformationWorkflow:
        """
        Find and recover workflow when you're not sure which mesh to select.
        This method searches the scene for likely base meshes with blendShapes.
        """
        pm.displayInfo("Searching scene for existing blendShape systems...")

        # Find all meshes with blendShape deformers
        meshes_with_blendshapes = []
        for node in pm.ls(type="transform"):
            try:
                if hasattr(node, "getShape") and node.getShape():
                    history = node.listHistory(type="blendShape")
                    if history:
                        meshes_with_blendshapes.append(node)
            except:
                continue

        if not meshes_with_blendshapes:
            pm.warning("No meshes with blendShape deformers found in scene.")
            pm.displayInfo("You may need to:")
            pm.displayInfo("1. Select your original base mesh (not target)")
            pm.displayInfo("2. Create a new workflow")
            raise RuntimeError("No blendShape systems found")

        pm.displayInfo(f"Found {len(meshes_with_blendshapes)} meshes with blendShapes:")
        for i, mesh in enumerate(meshes_with_blendshapes):
            pm.displayInfo(f"  {i+1}. {mesh}")

        # Try to get workflow from the first valid one
        for mesh in meshes_with_blendshapes:
            try:
                pm.select(mesh, replace=True)
                workflow = cls.get_workflow()
                pm.displayInfo(f"Successfully recovered workflow from: {mesh}")
                return workflow
            except Exception:
                continue

        # If we get here, all have issues - try repair on the first one
        pm.warning("All blendShape systems appear corrupted. Attempting repair...")
        pm.select(meshes_with_blendshapes[0], replace=True)
        return cls.get_or_create_workflow()

    # ===========================================================================
    # Static Convenience Methods
    # ===========================================================================

    @staticmethod
    def quick_workflow_setup(
        corrective_count: int = 3,
        animation_range: Tuple[int, int] = (5500, 5800),
        system_name: str = "quickDeformation",
    ) -> BlendShapeDeformationWorkflow:
        """
        Quick workflow setup: create deformation system and correctives in one operation.

        Args:
            corrective_count: Number of corrective shapes to create
            animation_range: Animation time range
            system_name: Name for deformation system

        Returns:
            Configured workflow ready for corrective editing

        Raises:
            RuntimeError: If workflow initialization fails
        """
        workflow = BlendShapeDeformationWorkflow()

        # Initialize deformation system
        if not workflow.initialize_deformation_system(
            animation_range=animation_range, system_name=system_name
        ):
            raise RuntimeError("Failed to initialize deformation system")

        # Create corrective shapes - use sample_count parameter
        correctives = workflow.create_corrective_shapes(sample_count=corrective_count)

        pm.displayInfo(
            f"Quick setup complete: {len(correctives)} correctives ready for editing"
        )
        pm.displayInfo(
            "Edit corrective geometry, then call workflow.apply_corrective_modifications()"
        )

        return workflow

    @staticmethod
    def batch_apply_correctives_to_selection() -> int:
        """Apply corrective modifications to all selected base geometries with blendShapes."""
        application_count = 0

        for geometry_node in pm.selected():
            try:
                workflow = (
                    BlendShapeDeformationWorkflow.load_existing_deformation_system(
                        geometry_node
                    )
                )
                if workflow:
                    correctives = workflow.apply_corrective_modifications()
                    application_count += len(correctives)
            except Exception as e:
                pm.warning(f"Failed to process {geometry_node}: {e}")

        pm.displayInfo(
            f"Batch applied {application_count} correctives across "
            f"{len(pm.selected())} geometry objects"
        )
        return application_count

    @staticmethod
    def quick_resample(resolution: int = 10) -> List[CorrectiveShape]:
        """
        Quick method to resample any existing animation in the scene.
        Useful for preserving work before system changes.

        Args:
            resolution: Number of sample points to create

        Returns:
            List of created corrective samples
        """
        try:
            workflow = BlendShapeDeformationWorkflow.get_workflow_auto()
            return workflow.resample_animation(resolution=resolution)
        except Exception as e:
            pm.error(f"Quick resample failed: {e}")
            return []

    @staticmethod
    def resample_and_rebuild_current(
        resolution: int = 10,
    ) -> BlendShapeDeformationWorkflow:
        """
        Quick method to resample current work and rebuild a clean system.
        Preserves your tween edits when the blendShape system gets corrupted.

        Args:
            resolution: Number of sample points to preserve

        Returns:
            New clean workflow with preserved work
        """
        try:
            workflow = BlendShapeDeformationWorkflow.get_workflow_auto()
            return workflow.resample_and_rebuild(resolution=resolution)
        except Exception as e:
            pm.error(f"Resample and rebuild failed: {e}")
            raise

    @staticmethod
    def restore_editable_morph_system() -> BlendShapeDeformationWorkflow:
        """
        Streamlined method to restore an editable morph animation system.
        Handles corrupted systems, preserves existing correctives, and sets up clean workflow.

        Usage: Select your base mesh, then call this method.

        Returns:
            Ready-to-edit workflow with preserved correctives
        """
        try:
            selection = pm.selected()
            if not selection:
                raise RuntimeError("Please select the base mesh to restore")

            base_mesh = selection[0]
            pm.displayInfo(f"Restoring editable morph system for: {base_mesh}")

            # Step 1: Discover existing correctives in the scene
            existing_correctives = CorrectiveManager.discover_scene_correctives()
            pm.displayInfo(
                f"Found {len(existing_correctives)} existing correctives to preserve"
            )

            # Step 2: Find the original target mesh if it exists
            original_target = None
            base_name = str(base_mesh).split("|")[-1]

            # Look for common target naming patterns
            possible_targets = [
                f"{base_name}_target",
                f"{base_name}_morph",
                f"{base_name}_blend",
                base_name.replace("_LOC", "_target"),
                base_name.replace("_LOC", "_morph"),
            ]

            for target_name in possible_targets:
                if pm.objExists(target_name):
                    original_target = pm.PyNode(target_name)
                    pm.displayInfo(f"Found original target: {original_target}")
                    break

            # Step 3: Clean up any corrupted blendShape deformers
            history = base_mesh.listHistory(type="blendShape")
            if history:
                pm.displayInfo("Removing corrupted blendShape deformers...")
                for old_bs in history:
                    try:
                        pm.delete(old_bs)
                    except:
                        pass

            # Step 4: Create or find target mesh
            if not original_target:
                # Create new target if none found
                clean_name = (
                    base_name.replace("|", "_").replace(":", "_").replace(" ", "_")
                )
                target_name = f"{clean_name}_morph"
                original_target = pm.duplicate(base_mesh, name=target_name)[0]
                pm.displayInfo(f"Created new target: {original_target}")

            # Step 5: Create clean workflow
            workflow = BlendShapeDeformationWorkflow()
            success = workflow.initialize_deformation_system(
                base_mesh,
                original_target,
                system_name=f"{base_name.split('|')[-1]}_restored",
            )

            if not success:
                raise RuntimeError("Failed to create clean workflow")

            # Step 6: Restore existing correctives if we have them
            if existing_correctives:
                pm.displayInfo("Restoring existing correctives...")
                try:
                    # Update corrective references to new system
                    updated_correctives = (
                        CorrectiveManager.update_corrective_references(
                            workflow.deformation_controller.blendshape_node,
                            workflow.deformation_controller.base_geometry,
                        )
                    )

                    # Apply the preserved correctives
                    applied_correctives = workflow.apply_corrective_modifications(
                        updated_correctives
                    )
                    pm.displayInfo(f"Restored {len(applied_correctives)} correctives")

                except Exception as restore_error:
                    pm.warning(f"Could not restore all correctives: {restore_error}")
                    pm.displayInfo("You may need to recreate some correctives manually")

            # Step 7: Organize everything
            workflow._auto_organize_if_needed()

            pm.displayInfo("=== RESTORATION COMPLETE ===")
            pm.displayInfo(f"✓ Clean blendShape system created")
            pm.displayInfo(f"✓ Target mesh: {original_target}")
            pm.displayInfo(f"✓ Preserved {len(existing_correctives)} correctives")
            pm.displayInfo("✓ System ready for editing")
            pm.displayInfo("")
            pm.displayInfo("Next steps:")
            pm.displayInfo("1. Edit your target mesh for the main morph shape")
            pm.displayInfo(
                "2. Edit correctives: workflow.edit_corrective_frame(weight)"
            )
            pm.displayInfo(
                "3. Create new correctives: workflow.create_corrective_shapes()"
            )

            return workflow

        except Exception as e:
            pm.error(f"Morph system restoration failed: {e}")
            raise

    @staticmethod
    def safe_get_workflow(
        base_geometry: Optional[pm.PyNode] = None,
    ) -> BlendShapeDeformationWorkflow:
        """
        DEPRECATED: Use get_or_create_workflow() instead.
        This method is kept for backward compatibility.
        """
        pm.warning(
            "safe_get_workflow() is deprecated. Use get_or_create_workflow() instead."
        )
        return BlendShapeDeformationWorkflow.get_or_create_workflow()

    @classmethod
    def diagnose_blendshape_system(
        cls, base_geometry: Optional[pm.PyNode] = None
    ) -> Dict:
        """
        Diagnose a blendShape system and return detailed information about its state.

        Args:
            base_geometry: Mesh to diagnose, or None to use selection

        Returns:
            Dictionary with diagnostic information
        """
        if base_geometry is None:
            selection = pm.selected()
            if not selection:
                return {"error": "No objects selected"}
            base_geometry = selection[0]

        diagnostic_info = {
            "mesh_name": str(base_geometry),
            "is_valid_mesh": False,
            "has_blendshape": False,
            "blendshape_nodes": [],
            "target_count": 0,
            "targets": [],
            "correctives_found": 0,
            "issues": [],
            "can_recover": False,
        }

        try:
            # Check if it's a valid mesh
            GeometryValidator.validate_mesh_transform(base_geometry)
            diagnostic_info["is_valid_mesh"] = True
        except (TypeError, ValueError) as e:
            diagnostic_info["issues"].append(f"Invalid mesh: {e}")
            return diagnostic_info

        # Check for blendShape deformers
        deformation_history = base_geometry.listHistory(type="blendShape")
        if deformation_history:
            diagnostic_info["has_blendshape"] = True
            diagnostic_info["blendshape_nodes"] = [
                str(node) for node in deformation_history
            ]

            blendshape_node = deformation_history[0]

            # Check targets
            try:
                target_geometries = (
                    pm.blendShape(blendshape_node, query=True, target=True) or []
                )
                diagnostic_info["target_count"] = len(target_geometries)
                diagnostic_info["targets"] = target_geometries

                if not target_geometries:
                    diagnostic_info["issues"].append(
                        "BlendShape has no target geometries"
                    )
                    diagnostic_info["can_recover"] = True
                else:
                    # Check if targets still exist
                    for target in target_geometries:
                        if not pm.objExists(target):
                            diagnostic_info["issues"].append(
                                f"Target geometry '{target}' no longer exists"
                            )

            except Exception as e:
                diagnostic_info["issues"].append(f"Error querying targets: {e}")
        else:
            diagnostic_info["issues"].append("No blendShape deformer found")

        # Check for existing correctives
        try:
            correctives = CorrectiveManager.discover_scene_correctives()
            diagnostic_info["correctives_found"] = len(correctives)
        except:
            diagnostic_info["correctives_found"] = 0

        return diagnostic_info


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    # ============================================================
    # STREAMLINED WORKFLOW - EVERYTHING AUTOMATIC
    # ============================================================

    try:
        # Check if we need restoration first
        selection = pm.selected()
        existing_correctives = CorrectiveManager.discover_scene_correctives()

        if existing_correctives and selection:
            # We have correctives but might have system issues - use restoration
            pm.displayInfo(
                f"Found {len(existing_correctives)} existing correctives - using restoration workflow..."
            )
            workflow = BlendShapeDeformationWorkflow.restore_editable_morph_system()
        else:
            # Standard workflow
            workflow = BlendShapeDeformationWorkflow.get_workflow_auto()

        # Show what we have
        workflow.show_status()

        # List any existing corrective frames
        correctives = workflow.list_corrective_frames()

        if correctives:
            pm.displayInfo("Ready to edit existing correctives!")
            pm.displayInfo("Use: workflow.edit_corrective_frame(weight)")
        else:
            pm.displayInfo("No correctives found. Create some first:")
            pm.displayInfo("Use: workflow.create_corrective_shapes()")

    except Exception as e:
        pm.error(f"Workflow failed: {e}")
        pm.displayInfo("=== RECOVERY OPTIONS ===")
        pm.displayInfo(
            "1. RESTORE CORRUPTED SYSTEM: BlendShapeDeformationWorkflow.restore_editable_morph_system()"
        )
        pm.displayInfo(
            "2. WRONG SELECTION? Select your ORIGINAL BASE MESH (not target)"
        )
        pm.displayInfo(
            "3. LOST WORKFLOW? Try: BlendShapeDeformationWorkflow.find_and_recover_workflow()"
        )
        pm.displayInfo(
            "4. START FRESH? Try: BlendShapeDeformationWorkflow.create_new()"
        )

    # ============================================================
    # STREAMLINED EXAMPLES - EVERYTHING AUTOMATIC:
    # ============================================================

    # Get any workflow (creates if needed, organizes automatically):
    # workflow = BlendShapeDeformationWorkflow.get_workflow_auto()

    # Restore corrupted system while preserving correctives (RECOMMENDED):
    # workflow = BlendShapeDeformationWorkflow.restore_editable_morph_system()

    # Create new workflow from scratch:
    # workflow = BlendShapeDeformationWorkflow.create_new()

    # Edit existing corrective at 50% deformation:
    # workflow.edit_corrective_frame(0.5)

    # Create 3 corrective shapes (auto-organized):
    # workflow.create_corrective_shapes(count=3)

    # Quick setup for new morph (creates workflow + correctives):
    # workflow = BlendShapeDeformationWorkflow.quick_setup()

    # ============================================================
    # RESAMPLE & PRESERVE WORK:
    # ============================================================

    # Preserve current tween work by resampling (10 samples):
    # samples = BlendShapeDeformationWorkflow.quick_resample(resolution=10)

    # Resample current animation to smooth it out:
    # workflow.resample_animation(resolution=15, preserve_existing=True)

    # Rebuild corrupted system while preserving work:
    # new_workflow = BlendShapeDeformationWorkflow.resample_and_rebuild_current(resolution=10)

    # Resample and rebuild from existing workflow:
    # new_workflow = workflow.resample_and_rebuild(resolution=12)

    # ============================================================
    # ANIMATION RECOVERY:
    # ============================================================

    # If you lost your previous animation, restore it with known frame range:
    # workflow.restore_animation_from_range(5500, 5800)  # Your previous range

    # Or just update the animation range:
    # workflow.update_animation_range(5500, 5800)

    # ============================================================
    # WORKFLOW RECOVERY:
    # ============================================================

    # If you can't find your workflow, let the system search for it:
    # workflow = BlendShapeDeformationWorkflow.find_and_recover_workflow()

    # If you selected the wrong mesh, select the ORIGINAL BASE MESH and try again
    # Look for names like "S00C27_CON_HOSE_LOC" (NOT "S00C27_CON_HOSE_LOC_target")

    # ============================================================
    # ORGANIZATION & CLEANUP - MOSTLY AUTOMATIC:
    # ============================================================

    # Manual organization (usually not needed - happens automatically):
    # workflow.organize_workflow_objects()

    # Clean up temporary objects:
    # AssetOrganizer.cleanup_temporary_objects()

    # Show organization summary:
    # print(AssetOrganizer.get_organization_summary())

    # Finalize workflow with full cleanup:
    # workflow.finalize_workflow()

    # Note: Organization happens automatically in most operations now!
# -----------------------------------------------------------------------------
# Notes: Workflow is now streamlined - organization happens automatically
# -----------------------------------------------------------------------------
