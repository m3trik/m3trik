from email.mime import base
import pymel.core as pm
from typing import List, Tuple, Optional, Union
from abc import ABC, abstractmethod
from functools import partial


class Validator:
    """Handles validation of meshes and blendShape setups."""

    @staticmethod
    def validate_meshes(mesh1: pm.PyNode, mesh2: pm.PyNode) -> bool:
        """Validate that both objects are compatible meshes."""
        # Check if objects are mesh transforms
        for i, mesh in enumerate([mesh1, mesh2], 1):
            if not mesh.getShape() or not isinstance(
                mesh.getShape(), pm.nodetypes.Mesh
            ):
                print(f"ERROR: Object {i} ({mesh}) is not a polygon mesh")
                return False

        # Check vertex counts match
        verts1 = mesh1.getShape().numVertices()
        verts2 = mesh2.getShape().numVertices()

        if verts1 != verts2:
            print(
                f"ERROR: Vertex count mismatch - {mesh1}: {verts1}, {mesh2}: {verts2}"
            )
            return False

        print(f"Mesh validation passed - both have {verts1} vertices")
        return True

    @staticmethod
    def validate_blendshape(blendshape: pm.PyNode) -> bool:
        """Validate blendShape node configuration."""
        if not pm.objExists(blendshape):
            print(f"ERROR: BlendShape {blendshape} does not exist")
            return False

        # Check envelope
        envelope = pm.getAttr(f"{blendshape}.envelope")
        if envelope != 1.0:
            print(f"WARNING: BlendShape envelope is {envelope}, should be 1.0")

        # Check weight attribute
        weight_attr = f"{blendshape}.weight[0]"
        if pm.getAttr(weight_attr, lock=True):
            print(f"WARNING: BlendShape weight is locked")

        return True


class Weights:
    """Handles weight calculations and Maya's precision requirements."""

    PRECISION = 3  # Maya requires 3 decimal places max

    @classmethod
    def round_weight(cls, weight: float) -> float:
        """Round weight to Maya-compatible precision."""
        return round(float(weight), cls.PRECISION)

    @classmethod
    def frame_to_weight(cls, frame: int, start_frame: int, end_frame: int) -> float:
        """Convert frame number to blendShape weight."""
        if frame <= start_frame:
            return 0.0
        if frame >= end_frame:
            return 1.0

        frame_range = end_frame - start_frame
        frame_offset = frame - start_frame
        return cls.round_weight(frame_offset / float(frame_range))

    @classmethod
    def generate_weights(
        cls,
        count: int,
        weight_range: Tuple[float, float] = (0.0, 1.0),
        include_endpoints: bool = False,
    ) -> List[float]:
        """Generate evenly spaced weights."""
        start, end = weight_range

        if include_endpoints:
            weights = [
                start + (end - start) * i / float(count) for i in range(0, count + 1)
            ]
        else:
            step = (end - start) / float(count + 1)
            weights = [start + step * i for i in range(1, count + 1)]

        return [cls.round_weight(w) for w in weights]


class Target:
    """Represents a single target/in-between target mesh."""

    def __init__(self, mesh: pm.PyNode):
        self.mesh = mesh
        self._validate_target_mesh()

    def _validate_target_mesh(self):
        """Validate this is a proper target mesh."""
        required_attrs = [
            "isInbetweenTarget",
            "inbetweenWeight",
            "blendShapeNode",
            "baseMesh",
        ]
        for attr in required_attrs:
            if not self.mesh.hasAttr(attr):
                raise ValueError(f"Mesh {self.mesh} missing required attribute: {attr}")

    @property
    def weight(self) -> float:
        """Get the weight value for this tween."""
        return Weights.round_weight(pm.getAttr(f"{self.mesh}.inbetweenWeight"))

    @property
    def blendshape_name(self) -> str:
        """Get the blendShape node name this tween targets."""
        return str(pm.getAttr(f"{self.mesh}.blendShapeNode"))

    @property
    def base_mesh_name(self) -> str:
        """Get the base mesh name this tween applies to."""
        return str(pm.getAttr(f"{self.mesh}.baseMesh"))

    @property
    def target_frame(self) -> Optional[int]:
        """Get target frame if this tween was created from a specific frame."""
        if self.mesh.hasAttr("targetFrame"):
            return int(pm.getAttr(f"{self.mesh}.targetFrame"))
        return None

    def update_references(self, new_blendshape: pm.PyNode, new_base_mesh: pm.PyNode):
        """Update this tween's references to new blendShape/base mesh."""
        pm.setAttr(f"{self.mesh}.blendShapeNode", str(new_blendshape), type="string")
        pm.setAttr(f"{self.mesh}.baseMesh", str(new_base_mesh), type="string")
        print(f"  Updated {self.mesh.name()} references")


class Targets:
    """Manages collections of tween meshes."""

    DEFAULT_GROUPS = ["_morphInbetweens_GRP", "_preciseTweens_GRP"]

    @classmethod
    def find_all_targets(cls) -> List[Target]:
        """Find all tween meshes in the scene."""
        candidates = []

        # Check in known groups
        for group_name in cls.DEFAULT_GROUPS:
            if pm.objExists(group_name):
                group = pm.PyNode(group_name)
                children = (
                    pm.listRelatives(group, children=True, type="transform") or []
                )
                candidates.extend(children)

        # Check loose tween meshes
        loose_tweens = [
            n for n in pm.ls(type="transform") if n.hasAttr("isInbetweenTarget")
        ]
        candidates.extend(loose_tweens)

        # Convert to Target objects and validate
        tweens = []
        for mesh in candidates:
            try:
                if mesh.hasAttr("isInbetweenTarget") and pm.getAttr(
                    f"{mesh}.isInbetweenTarget"
                ):
                    tweens.append(Target(mesh))
            except ValueError:
                print(f"Skipping invalid tween mesh: {mesh}")
                continue

        return sorted(tweens, key=lambda t: t.weight)

    @classmethod
    def group_by_weight(cls, tweens: List[Target]) -> dict:
        """Group tweens by weight value, handling duplicates."""
        weight_groups = {}
        for tween in tweens:
            w = tween.weight
            if w not in weight_groups:
                weight_groups[w] = []
            weight_groups[w].append(tween)
        return weight_groups

    @classmethod
    def update_all_references(
        cls, new_blendshape: pm.PyNode, new_base_mesh: pm.PyNode
    ) -> int:
        """Update all tween mesh references to new nodes."""
        tweens = cls.find_all_targets()
        for tween in tweens:
            tween.update_references(new_blendshape, new_base_mesh)
        print(f"Updated {len(tweens)} tween references")
        return len(tweens)


class Keyframes:
    """Core blendShape animation functionality."""

    def __init__(
        self, base_mesh: pm.PyNode, target_mesh: pm.PyNode, blendshape: pm.PyNode
    ):
        self.base_mesh = base_mesh
        self.target_mesh = target_mesh
        self.blendshape = blendshape
        self.validator = Validator()

    def create_keyframes(self, start_frame: int, end_frame: int) -> bool:
        """Create linear keyframe animation."""
        try:
            # Clear existing keys
            pm.cutKey(self.blendshape, attribute="weight[0]", clear=True)

            # Set start key (weight = 0)
            pm.currentTime(start_frame)
            pm.setKeyframe(
                self.blendshape, attribute="weight[0]", value=0.0, time=start_frame
            )

            # Set end key (weight = 1)
            pm.currentTime(end_frame)
            pm.setKeyframe(
                self.blendshape, attribute="weight[0]", value=1.0, time=end_frame
            )

            # Set linear tangents
            pm.keyTangent(
                self.blendshape,
                attribute="weight[0]",
                time=(start_frame, end_frame),
                inTangentType="linear",
                outTangentType="linear",
            )

            print(f"Created keyframes: {start_frame} to {end_frame}")
            return True

        except Exception as e:
            print(f"ERROR creating keyframes: {e}")
            return False

    def test_morph(self) -> bool:
        """Test the blendShape by temporarily setting weight to 0.5."""
        if not self.validator.validate_blendshape(self.blendshape):
            return False

        original_weight = pm.getAttr(f"{self.blendshape}.weight[0]")

        try:
            pm.setAttr(f"{self.blendshape}.weight[0]", 0.5)
            pm.refresh()
            print(f"BlendShape test: weight set to 0.5")
            print(f"Check if {self.base_mesh} changed shape (should morph, not move)")
            return True
        finally:
            pm.setAttr(f"{self.blendshape}.weight[0]", original_weight)

    def get_frame_range(self) -> Tuple[int, int]:
        """Get the current animation frame range from keyframes."""
        keys = pm.keyframe(f"{self.blendshape}.weight[0]", query=True)
        if not keys or len(keys) < 2:
            raise ValueError("No valid keyframe range found")
        return int(min(keys)), int(max(keys))


class Creator:
    """Creates in-between target meshes for custom animation curves."""

    def __init__(self, animator: Keyframes):
        self.animator = animator

    def create_weight_based_tweens(
        self,
        weights: List[float],
        group_name: str = "_morphInbetweens_GRP",
        name_prefix: str = "morph_ib",
    ) -> List[Target]:
        """Create tween meshes at specific weight values."""
        original_weight = pm.getAttr(f"{self.animator.blendshape}.weight[0]")
        created_tweens = []

        # Create/get group
        if not pm.objExists(group_name):
            group = pm.group(empty=True, name=group_name)
        else:
            group = pm.PyNode(group_name)

        try:
            for weight in weights:
                weight = Weights.round_weight(weight)

                # Set weight and capture shape
                pm.setAttr(f"{self.animator.blendshape}.weight[0]", weight)
                pm.refresh()

                # Create duplicate
                tween_name = f"{name_prefix}_w{int(weight * 1000):03d}"
                dup = pm.duplicate(
                    self.animator.base_mesh, name=tween_name, returnRootsOnly=True
                )[0]
                pm.delete(dup, constructionHistory=True)

                # Reset weight before creating in-between target
                pm.setAttr(f"{self.animator.blendshape}.weight[0]", 0.0)
                pm.refresh()

                # Parent to group
                pm.parent(dup, group)

                # Create in-between target
                pm.blendShape(
                    self.animator.blendshape,
                    edit=True,
                    inBetween=True,
                    target=(self.animator.base_mesh, 0, dup, weight),
                )

                # Tag with metadata
                self._tag_tween_mesh(dup, weight)
                created_tweens.append(Target(dup))

        finally:
            pm.setAttr(f"{self.animator.blendshape}.weight[0]", original_weight)

        print(
            f"Created {len(created_tweens)} tween meshes at weights: {[t.weight for t in created_tweens]}"
        )
        return created_tweens

    def create_frame_based_tween(self, target_frame: int) -> Optional[Target]:
        """Create a tween mesh at a specific animation frame."""
        try:
            start_frame, end_frame = self.animator.get_frame_range()
        except ValueError as e:
            print(f"ERROR: {e}")
            return None

        if not (start_frame < target_frame < end_frame):
            print(
                f"ERROR: Frame {target_frame} must be between {start_frame} and {end_frame}"
            )
            return None

        weight = Weights.frame_to_weight(target_frame, start_frame, end_frame)

        # Check if weight already exists
        existing_weights = self._get_existing_weights()
        if weight in existing_weights:
            print(
                f"WARNING: Weight {weight:.3f} already exists for frame {target_frame}"
            )
            print(f"Existing in-between weights: {sorted(existing_weights)}")

            # Offer to create at slightly different weight
            offset_weight = self._find_nearby_weight(weight, existing_weights)
            if offset_weight:
                print(f"Creating tween at nearby weight {offset_weight:.3f} instead")
                weight = offset_weight
            else:
                print("Cannot find suitable alternative weight")
                return None

        original_weight = pm.getAttr(f"{self.animator.blendshape}.weight[0]")
        original_time = pm.currentTime(query=True)

        try:
            # Go to target frame and set weight
            pm.currentTime(target_frame)
            pm.setAttr(f"{self.animator.blendshape}.weight[0]", weight)
            pm.refresh()

            # Create tween
            tween_name = f"tween_f{target_frame}_w{int(weight * 1000):03d}"
            dup = pm.duplicate(
                self.animator.base_mesh, name=tween_name, returnRootsOnly=True
            )[0]
            pm.delete(dup, constructionHistory=True)

            # Reset and create in-between
            pm.setAttr(f"{self.animator.blendshape}.weight[0]", 0.0)
            pm.refresh()

            try:
                pm.blendShape(
                    self.animator.blendshape,
                    edit=True,
                    inBetween=True,
                    target=(self.animator.base_mesh, 0, dup, weight),
                )
            except Exception as e:
                if "Weights must be unique" in str(e):
                    print(f"ERROR: Weight {weight:.3f} already exists in blendShape")
                    pm.delete(dup)  # Clean up the duplicate
                    return None
                else:
                    raise e

            # Tag with metadata including frame info
            self._tag_tween_mesh(dup, weight, target_frame)

            # Group it
            group_name = "_morphInbetweens_GRP"
            if not pm.objExists(group_name):
                group = pm.group(empty=True, name=group_name)
            else:
                group = pm.PyNode(group_name)
            pm.parent(dup, group)

            print(
                f"Created frame-based tween: {tween_name} (frame {target_frame}, weight {weight:.3f})"
            )
            return Target(dup)

        finally:
            pm.setAttr(f"{self.animator.blendshape}.weight[0]", original_weight)
            pm.currentTime(original_time)

    def _tag_tween_mesh(
        self, mesh: pm.PyNode, weight: float, target_frame: Optional[int] = None
    ):
        """Add metadata attributes to tween mesh."""
        # Basic tween attributes
        pm.addAttr(
            mesh, longName="isInbetweenTarget", attributeType="bool", keyable=False
        )
        pm.setAttr(f"{mesh}.isInbetweenTarget", True)

        pm.addAttr(
            mesh, longName="inbetweenWeight", attributeType="double", keyable=False
        )
        pm.setAttr(f"{mesh}.inbetweenWeight", weight)

        pm.addAttr(mesh, longName="blendShapeNode", dataType="string")
        pm.setAttr(
            f"{mesh}.blendShapeNode", str(self.animator.blendshape), type="string"
        )

        pm.addAttr(mesh, longName="baseMesh", dataType="string")
        pm.setAttr(f"{mesh}.baseMesh", str(self.animator.base_mesh), type="string")

        # Optional frame information
        if target_frame is not None:
            pm.addAttr(
                mesh, longName="targetFrame", attributeType="long", keyable=False
            )
            pm.setAttr(f"{mesh}.targetFrame", target_frame)

    def _get_existing_weights(self) -> set:
        """Get all existing in-between weights for the current blendShape."""
        try:
            # Query existing in-between targets
            existing_weights = set()

            # Check for in-between targets using Maya's blendShape query
            targets = pm.blendShape(self.animator.blendshape, query=True, target=True)
            if targets:
                # Query in-between weights for the first target (index 0)
                try:
                    inbetween_weights = pm.blendShape(
                        self.animator.blendshape,
                        query=True,
                        inBetween=True,
                        target=(self.animator.base_mesh, 0),
                    )
                    if inbetween_weights:
                        existing_weights.update(inbetween_weights)
                except:
                    pass  # No in-betweens exist yet

            # Also check tween meshes that might exist in scene
            tweens = Targets.find_all_targets()
            for tween in tweens:
                existing_weights.add(tween.weight)

            return existing_weights
        except:
            return set()

    def _find_nearby_weight(
        self, target_weight: float, existing_weights: set, tolerance: float = 0.01
    ) -> Optional[float]:
        """Find a nearby weight that doesn't conflict with existing weights."""
        # Try small offsets around the target weight
        for offset in [0.001, -0.001, 0.002, -0.002, 0.005, -0.005, 0.01, -0.01]:
            candidate = Weights.round_weight(target_weight + offset)
            if 0.0 < candidate < 1.0 and candidate not in existing_weights:
                return candidate
        return None


class Applicator:
    """Applies tween mesh edits back to blendShape in-between targets."""

    def __init__(self, animator: Keyframes):
        self.animator = animator

    def validate_topology(self, tweens: List[Target]) -> List[Target]:
        """Validate and filter tweens that match base mesh topology."""
        print("Validating tween mesh topology...")

        base_vert_count = self.animator.base_mesh.getShape().numVertices()
        valid_tweens = []

        for tween in tweens:
            try:
                tween_vert_count = tween.mesh.getShape().numVertices()
                if tween_vert_count == base_vert_count:
                    valid_tweens.append(tween)
                    print(
                        f"  ✓ {tween.mesh.name()}: {tween_vert_count} vertices (valid)"
                    )
                else:
                    print(
                        f"  ✗ {tween.mesh.name()}: {tween_vert_count} vs {base_vert_count} vertices (topology mismatch)"
                    )
            except Exception as e:
                print(f"  ✗ {tween.mesh.name()}: Error checking topology - {e}")

        if len(valid_tweens) != len(tweens):
            print(
                f"Filtered {len(tweens) - len(valid_tweens)} tweens due to topology mismatch"
            )

        return valid_tweens

    def apply_tweens(
        self,
        tweens: Optional[List[Target]] = None,
        skip_duplicates: bool = True,
        validate_topology: bool = True,
    ) -> List[Tuple[Target, bool]]:
        """Apply tween mesh edits to blendShape in-between targets."""
        if tweens is None:
            tweens = Targets.find_all_targets()

        if not tweens:
            print("No tween meshes found to apply")
            return []

        # Validate topology if requested
        if validate_topology:
            tweens = self.validate_topology(tweens)
            if not tweens:
                print("No valid tweens found after topology validation")
                return []

        # Group by weight to handle duplicates
        weight_groups = Targets.group_by_weight(tweens)
        applied_results = []
        original_weight = pm.getAttr(f"{self.animator.blendshape}.weight[0]")

        try:
            for weight, tween_group in sorted(weight_groups.items()):
                # Use the last (most recent) tween for each weight
                target_tween = tween_group[-1]

                if len(tween_group) > 1:
                    print(
                        f"  Found {len(tween_group)} tweens at weight {weight:.3f}, using: {target_tween.mesh.name()}"
                    )

                # Apply this tween
                success = self._apply_single_tween(target_tween, skip_duplicates)
                applied_results.append((target_tween, success))

                if success:
                    print(f"Applied {target_tween.mesh.name()} at weight {weight:.3f}")
                else:
                    print(f"Failed to apply {target_tween.mesh.name()}")

        finally:
            pm.setAttr(f"{self.animator.blendshape}.weight[0]", original_weight)

        successful_count = sum(1 for _, success in applied_results if success)
        print(f"Applied {successful_count}/{len(applied_results)} tween edits")
        return applied_results

    def _apply_single_tween(self, tween: Target, skip_duplicates: bool) -> bool:
        """Apply a single tween mesh to the blendShape."""
        try:
            pm.blendShape(
                self.animator.blendshape,
                edit=True,
                inBetween=True,
                target=(self.animator.base_mesh, 0, tween.mesh, tween.weight),
            )
            return True

        except Exception as e:
            error_msg = str(e)
            if "Weights must be unique" in error_msg and skip_duplicates:
                print(f"    Skipped {tween.mesh.name()} (duplicate weight)")
                return False  # Not applied, but not an error
            else:
                print(f"    Error applying {tween.mesh.name()}: {e}")
                return False


class Animator:
    """Main workflow class for blendShape animations."""

    def __init__(self):
        self.base_mesh: Optional[pm.PyNode] = None
        self.target_mesh: Optional[pm.PyNode] = None
        self.blendshape: Optional[pm.PyNode] = None
        self.animator: Optional[Keyframes] = None
        self.tween_creator: Optional[Creator] = None
        self.tween_applicator: Optional[Applicator] = None

    def create(
        self,
        base_mesh: pm.PyNode = None,
        target_mesh: pm.PyNode = None,
        start_frame: int = 5500,
        end_frame: int = 5800,
        name: str = "morph",
        test_setup: bool = True,
    ) -> bool:
        """
        CREATE phase: Set up basic morph animation between two meshes.

        Args:
            base_mesh: Source mesh (will have blendShape applied)
            target_mesh: Target mesh (blendShape target)
            start_frame: Animation start frame
            end_frame: Animation end frame
            name: Name prefix for blendShape
            test_setup: Whether to test the setup after creation

        Returns:
            bool: True if setup successful
        """
        print("=== CREATE PHASE: Setting up morph animation ===")

        # Get meshes from selection if not provided
        if base_mesh is None or target_mesh is None:
            selection = pm.selected()
            if len(selection) != 2:
                print(
                    "ERROR: Please select exactly 2 meshes (source first, target second)"
                )
                return False
            base_mesh, target_mesh = selection[0], selection[1]

        # Validate meshes
        if not Validator.validate_meshes(base_mesh, target_mesh):
            return False

        self.base_mesh = base_mesh
        self.target_mesh = target_mesh

        # Create or find blendShape
        try:
            history = base_mesh.listHistory(type="blendShape")
            if history:
                self.blendshape = history[0]
                print(f"Found existing blendShape: {self.blendshape}")
            else:
                blendshape_name = f"{name}_BS"
                self.blendshape = pm.blendShape(
                    target_mesh,
                    base_mesh,
                    name=blendshape_name,
                    frontOfChain=True,
                    origin="world",
                )[0]
                print(f"Created blendShape: {self.blendshape}")

            # Configure blendShape
            pm.setAttr(f"{self.blendshape}.weight[0]", keyable=True, lock=False)
            pm.setAttr(f"{self.blendshape}.envelope", 1.0)

            # Create animator and sub-components
            self.animator = Keyframes(self.base_mesh, self.target_mesh, self.blendshape)
            self.tween_creator = Creator(self.animator)
            self.tween_applicator = Applicator(self.animator)

            # Create keyframes
            if not self.animator.create_keyframes(start_frame, end_frame):
                return False

            # Test setup
            if test_setup:
                print("\nTesting blendShape setup...")
                self.animator.test_morph()

            print(f"CREATE phase complete: {base_mesh} → {target_mesh}")
            print(f"Animation range: {start_frame} to {end_frame}")
            return True

        except Exception as e:
            print(f"ERROR in CREATE phase: {e}")
            return False

    def edit(self, mode: str = "weights", **kwargs) -> List[Target]:
        """
        EDIT phase: Add and customize in-between targets.

        Args:
            mode: "weights", "frames", or "apply"
            **kwargs: Mode-specific parameters

        Returns:
            List[Target]: Created or applied tween meshes
        """
        if not self._validate_setup():
            return []

        if mode == "weights":
            return self._edit_weight_based(**kwargs)
        elif mode == "frames":
            return self._edit_frame_based(**kwargs)
        elif mode == "apply":
            return self._edit_apply_tweens(**kwargs)
        else:
            print(
                f"ERROR: Unknown edit mode '{mode}'. Use 'weights', 'frames', or 'apply'"
            )
            return []

    def _edit_weight_based(
        self,
        weights: List[float] = None,
        count: int = 3,
        weight_range: Tuple[float, float] = (0.0, 1.0),
    ) -> List[Target]:
        """Create tweens at specific weights or evenly spaced."""
        print("=== EDIT PHASE: Creating weight-based tweens ===")

        if weights is None:
            weights = Weights.generate_weights(count, weight_range)
        else:
            weights = [Weights.round_weight(w) for w in weights]

        tweens = self.tween_creator.create_weight_based_tweens(weights)

        if tweens:
            print(f"Edit these {len(tweens)} meshes to customize the morph curve")
            print("When done editing, run: edit(mode='apply')")

        return tweens

    def _edit_frame_based(
        self, frames: List[int] = None, target_frame: int = None
    ) -> List[Target]:
        """Create tweens at specific animation frames."""
        print("=== EDIT PHASE: Creating frame-based tweens ===")

        created_tweens = []

        if target_frame is not None:
            tween = self.tween_creator.create_frame_based_tween(target_frame)
            if tween:
                created_tweens.append(tween)

        if frames:
            for frame in frames:
                tween = self.tween_creator.create_frame_based_tween(frame)
                if tween:
                    created_tweens.append(tween)

        if created_tweens:
            print(
                f"Edit these {len(created_tweens)} meshes to customize specific frames"
            )
            print("When done editing, run: edit(mode='apply')")

        return created_tweens

    def _edit_apply_tweens(self, tweens: List[Target] = None) -> List[Target]:
        """Apply tween mesh edits back to blendShape."""
        print("=== EDIT PHASE: Applying tween edits ===")

        results = self.tween_applicator.apply_tweens(tweens)
        applied_tweens = [tween for tween, success in results if success]

        if applied_tweens:
            print("✓ Tween edits applied! Scrub timeline to see custom curve")

        return applied_tweens

    def _validate_setup(self) -> bool:
        """Validate that the setup is ready for operations."""
        if not all([self.base_mesh, self.target_mesh, self.blendshape, self.animator]):
            print("ERROR: Setup not complete. Run create() first.")
            return False
        return True

    def _process_existing_inbetweens(self, inbetween_meshes: List[pm.PyNode]):
        """Process existing in-between meshes and add them to the blendShape."""
        if not self._validate_setup():
            return

        print(f"Processing {len(inbetween_meshes)} existing in-between meshes...")

        # Calculate weights based on number of in-betweens
        count = len(inbetween_meshes)
        weights = Weights.generate_weights(count, (0.0, 1.0))

        for i, (mesh, weight) in enumerate(zip(inbetween_meshes, weights)):
            try:
                # Add as in-between target
                pm.blendShape(
                    self.blendshape,
                    edit=True,
                    inBetween=True,
                    target=(self.base_mesh, 0, mesh, weight),
                )

                # Tag the mesh with metadata
                self.tween_creator._tag_tween_mesh(mesh, weight)

                print(f"  Added {mesh.name()} as in-between at weight {weight:.3f}")

            except Exception as e:
                print(f"  Failed to add {mesh.name()}: {e}")

        print("Existing in-between meshes processed!")
        print("You can now edit these meshes and run: animator.apply_all_edits()")

    # =============================================================================
    # WORKFLOW CONVENIENCE METHODS
    # =============================================================================

    @classmethod
    def basic_workflow(
        cls,
        base_mesh=None,
        target_mesh=None,
        inbetween_meshes=None,
        start_frame=None,
        end_frame=None,
        frame_range=None,
        name="morph",
    ):
        """Complete basic workflow: Create setup with targets for editing.

        Args:
            base_mesh: Source mesh (will have blendShape applied)
            target_mesh: Target mesh (blendShape target)
            inbetween_meshes: List of existing in-between meshes to add
            start_frame: Animation start frame (ignored if frame_range provided)
            end_frame: Animation end frame (ignored if frame_range provided)
            frame_range: Tuple of (start_frame, end_frame) - overrides individual frame params
            name: Name prefix for blendShape

        Returns:
            Animator: Configured animator instance
        """
        print("=== BASIC WORKFLOW ===")

        # Handle frame_range parameter
        if frame_range is not None:
            if isinstance(frame_range, (tuple, list)) and len(frame_range) == 2:
                start_frame, end_frame = frame_range
            else:
                print(
                    "ERROR: frame_range must be a tuple/list of (start_frame, end_frame)"
                )
                return None

        # Step 1: CREATE
        animator = cls()
        success = animator.create(
            base_mesh=base_mesh,
            target_mesh=target_mesh,
            start_frame=start_frame,
            end_frame=end_frame,
            name=name,
            test_setup=True,
        )

        if not success:
            print("Setup failed. Check your mesh objects or selection.")
            return None

        # Step 2: Handle existing in-between meshes or create new ones
        if inbetween_meshes:
            print(f"\nProcessing {len(inbetween_meshes)} existing in-between meshes...")
            # Convert existing meshes to in-between targets
            animator._process_existing_inbetweens(inbetween_meshes)
        else:
            # Step 2: EDIT - Add 3 target points for custom curves
            print("\nCreating target meshes for custom animation curve...")
            targets = animator.edit(mode="weights", count=3)

            if targets:
                print(f"Created {len(targets)} target meshes")
                print("Now edit these meshes in Maya to customize your animation curve")
                print("When done editing, run: animator.apply_all_edits()")

        return animator

    def apply_all_edits(self):
        """Apply all target edits to the current setup."""
        print("=== APPLYING ALL TARGET EDITS ===")

        if not self._validate_setup():
            return False

        applied = self.edit(mode="apply")

        if applied:
            print(f"Applied {len(applied)} target edits!")
            print("Check your timeline - animation should now show custom curve")
            return True
        else:
            print("No target edits found to apply")
            return False

    def finalize_for_export(
        self,
        cleanup_scene=True,
        delete_construction_history=True,
        hide_target_mesh=True,
        delete_inbetween_meshes=True,
    ):
        """
        Finalize the morph animation and clean up scene for baking/export.

        Args:
            cleanup_scene: Remove temporary groups and in-between meshes
            delete_construction_history: Clean construction history on base mesh
            hide_target_mesh: Hide the original target mesh
            delete_inbetween_meshes: Delete the in-between mesh objects after applying

        Returns:
            bool: True if finalization successful
        """
        print("=== FINALIZING FOR EXPORT ===")

        if not self._validate_setup():
            return False

        # Step 1: Apply all edits
        print("Step 1: Applying all in-between edits...")
        applied = self.edit(mode="apply")

        if not applied:
            print("No edits to apply - continuing with cleanup...")
        else:
            print(f"Applied {len(applied)} in-between edits")

        # Step 2: Clean up scene
        if cleanup_scene:
            print("Step 2: Cleaning up scene...")

            # Hide/delete target mesh
            if hide_target_mesh and self.target_mesh:
                try:
                    pm.setAttr(f"{self.target_mesh}.visibility", False)
                    print(f"  Hidden target mesh: {self.target_mesh}")
                except:
                    print(f"  Could not hide target mesh: {self.target_mesh}")

            # Handle in-between meshes
            if delete_inbetween_meshes:
                tweens = Targets.find_all_targets()
                deleted_count = 0
                for tween in tweens:
                    try:
                        pm.delete(tween.mesh)
                        deleted_count += 1
                    except:
                        print(f"  Could not delete: {tween.mesh}")

                if deleted_count > 0:
                    print(f"  Deleted {deleted_count} in-between mesh objects")

                # Clean up empty groups
                for group_name in Targets.DEFAULT_GROUPS:
                    if pm.objExists(group_name):
                        group = pm.PyNode(group_name)
                        children = pm.listRelatives(group, children=True) or []
                        if not children:  # Empty group
                            try:
                                pm.delete(group)
                                print(f"  Deleted empty group: {group_name}")
                            except:
                                pass
            else:
                # Just hide the groups
                for group_name in Targets.DEFAULT_GROUPS:
                    if pm.objExists(group_name):
                        try:
                            pm.setAttr(f"{group_name}.visibility", False)
                            print(f"  Hidden group: {group_name}")
                        except:
                            pass

        # Step 3: Clean construction history
        if delete_construction_history and self.base_mesh:
            print("Step 3: Cleaning construction history...")
            try:
                # Don't delete the blendShape - only clean other history
                history = self.base_mesh.listHistory()
                to_delete = []
                for node in history:
                    if node.nodeType() not in ["blendShape", "mesh", "transform"]:
                        to_delete.append(node)

                if to_delete:
                    pm.delete(to_delete)
                    print(
                        f"  Cleaned {len(to_delete)} history nodes (preserved blendShape)"
                    )
                else:
                    print("  No unnecessary history to clean")
            except Exception as e:
                print(f"  Warning: Could not clean history completely: {e}")

        # Step 4: Final validation
        print("Step 4: Final validation...")
        try:
            # Test the blendShape one more time
            original_weight = pm.getAttr(f"{self.blendshape}.weight[0]")
            pm.setAttr(f"{self.blendshape}.weight[0]", 0.5)
            pm.refresh()
            pm.setAttr(f"{self.blendshape}.weight[0]", original_weight)
            print("  ✓ BlendShape validation passed")
        except Exception as e:
            print(f"  ⚠ BlendShape validation warning: {e}")

        # Summary
        print("\n=== EXPORT READY ===")
        print(f"✓ Base mesh: {self.base_mesh}")
        print(f"✓ BlendShape: {self.blendshape}")
        print(
            f"✓ Animation keyframes: {len(pm.keyframe(f'{self.blendshape}.weight[0]', query=True) or [])} keys"
        )
        print("✓ Scene cleaned and ready for baking/export")
        print("\nYou can now:")
        print("  - Bake the animation to keyframes")
        print("  - Export to FBX/other formats")
        print("  - Use in your final pipeline")

        return True

    @classmethod
    def from_existing(cls, base_mesh=None):
        """Create animator from existing blendShape setup."""
        print("=== LOADING EXISTING SETUP ===")

        # Use provided base_mesh or fallback to selection
        if base_mesh is None:
            selection = pm.selected()
            if selection:
                base_mesh = selection[0]
            else:
                print("No base mesh provided and nothing selected.")
                return None

        # Find blendShape
        history = base_mesh.listHistory(type="blendShape")
        if not history:
            print(f"No blendShape found on {base_mesh}")
            return None

        blendshape = history[0]

        # Find target mesh from blendShape - look for the original target, not in-betweens
        targets = pm.blendShape(blendshape, query=True, target=True)
        if not targets:
            print(f"No targets found in blendShape {blendshape}")
            return None

        # Try to find the main target (not an in-between mesh)
        target_mesh = None
        for target_name in targets:
            candidate = pm.PyNode(target_name)
            # Skip if it looks like an in-between mesh (has specific naming patterns)
            if not any(
                pattern in candidate.name() for pattern in ["tween_f", "_w0", "_ib_"]
            ):
                target_mesh = candidate
                break

        # If no good target found, use the first one but warn
        if target_mesh is None:
            target_mesh = pm.PyNode(targets[0])
            print(
                f"WARNING: Using {target_mesh} as target - might be an in-between mesh"
            )

        # Create and configure animator
        animator = cls()
        animator.base_mesh = base_mesh
        animator.target_mesh = target_mesh
        animator.blendshape = blendshape
        animator.animator = Keyframes(base_mesh, target_mesh, blendshape)
        animator.tween_creator = Creator(animator.animator)
        animator.tween_applicator = Applicator(animator.animator)

        # Check for existing keyframes
        existing_keys = pm.keyframe(f"{blendshape}.weight[0]", query=True) or []
        if existing_keys:
            print(f"Found {len(existing_keys)} existing keyframes")
        else:
            print("WARNING: No animation keyframes found")

        print(f"Loaded existing setup: {base_mesh} → {target_mesh}")
        return animator

    def recover_animation(self):
        """Recover lost animation keyframes and validate setup."""
        print("=== RECOVERING ANIMATION ===")

        if not self._validate_setup():
            return False

        # Check current keyframes
        current_keys = pm.keyframe(f"{self.blendshape}.weight[0]", query=True) or []

        if len(current_keys) >= 2:
            print(f"Animation already exists with {len(current_keys)} keyframes")
            return True

        print("No animation keyframes found - attempting recovery...")

        # Try to recover from tween metadata
        tweens = Targets.find_all_targets()
        if tweens:
            # Find frame range from tween metadata
            frames = []
            for tween in tweens:
                if tween.target_frame:
                    frames.append(tween.target_frame)

            if len(frames) >= 2:
                start_frame = min(frames)
                end_frame = max(frames)
                print(
                    f"Recovered frame range from tweens: {start_frame} to {end_frame}"
                )

                # Recreate keyframes
                success = self.animator.create_keyframes(start_frame, end_frame)
                if success:
                    print("✓ Animation keyframes recovered!")
                    return True

        # Fallback: create default animation
        print(
            "Could not recover original range - creating default animation (frames 1-100)"
        )
        success = self.animator.create_keyframes(1, 100)
        if success:
            print("✓ Default animation created")
            return True

        print("✗ Failed to recover animation")
        return False

    def diagnose_topology_issues(self):
        """Diagnose topology mismatches between base mesh and in-between meshes."""
        print("=== TOPOLOGY DIAGNOSIS ===")

        if not self._validate_setup():
            return False

        base_vert_count = self.base_mesh.getShape().numVertices()
        base_face_count = self.base_mesh.getShape().numFaces()

        print(
            f"Base mesh '{self.base_mesh}': {base_vert_count} vertices, {base_face_count} faces"
        )

        # Check target mesh
        try:
            target_vert_count = self.target_mesh.getShape().numVertices()
            target_face_count = self.target_mesh.getShape().numFaces()
            print(
                f"Target mesh '{self.target_mesh}': {target_vert_count} vertices, {target_face_count} faces"
            )

            if target_vert_count != base_vert_count:
                print(f"⚠ WARNING: Target mesh topology mismatch!")
        except:
            print(f"✗ ERROR: Cannot read target mesh topology")

        # Check in-between meshes
        tweens = Targets.find_all_targets()
        if not tweens:
            print("No in-between meshes found")
            return True

        print(f"\nChecking {len(tweens)} in-between meshes:")

        mismatched_count = 0
        for tween in tweens:
            try:
                tween_vert_count = tween.mesh.getShape().numVertices()
                tween_face_count = tween.mesh.getShape().numFaces()

                if (
                    tween_vert_count == base_vert_count
                    and tween_face_count == base_face_count
                ):
                    print(
                        f"  ✓ {tween.mesh.name()}: {tween_vert_count}v, {tween_face_count}f (MATCH)"
                    )
                else:
                    print(
                        f"  ✗ {tween.mesh.name()}: {tween_vert_count}v, {tween_face_count}f (MISMATCH)"
                    )
                    mismatched_count += 1
            except Exception as e:
                print(f"  ✗ {tween.mesh.name()}: Error - {e}")
                mismatched_count += 1

        if mismatched_count > 0:
            print(f"\n⚠ {mismatched_count} meshes have topology mismatches")
            print("\nPossible solutions:")
            print("1. Delete mismatched meshes and recreate them")
            print("2. Use Transfer Attributes to fix topology")
            print("3. Manually fix vertex counts in Maya")
            print("4. Start over with matching topology")
            return False
        else:
            print("\n✓ All meshes have matching topology")
            return True

    def cleanup_topology_mismatches(
        self, delete_mismatched=True, apply_valid_only=True
    ):
        """Clean up topology mismatches by deleting bad meshes and applying good ones."""
        print("=== CLEANING UP TOPOLOGY MISMATCHES ===")

        if not self._validate_setup():
            return False

        # Check target mesh topology first
        base_vert_count = self.base_mesh.getShape().numVertices()
        target_topology_mismatch = False

        try:
            target_vert_count = self.target_mesh.getShape().numVertices()
            if target_vert_count != base_vert_count:
                print(
                    f"Target mesh topology mismatch: {target_vert_count}v vs {base_vert_count}v"
                )
                target_topology_mismatch = True
            else:
                print(f"Target mesh topology OK: {target_vert_count}v")
        except:
            print("Cannot validate target mesh topology")
            target_topology_mismatch = True

        # Get all tweens and separate good from bad
        all_tweens = Targets.find_all_targets()
        if not all_tweens:
            print("No in-between meshes found")
            # Still handle target mesh if needed
            if target_topology_mismatch and delete_mismatched:
                self._cleanup_target_mesh()
            return True

        valid_tweens = self.tween_applicator.validate_topology(all_tweens)
        invalid_tweens = [t for t in all_tweens if t not in valid_tweens]

        print(
            f"Found {len(valid_tweens)} valid and {len(invalid_tweens)} invalid in-between meshes"
        )

        # Apply valid tweens first
        if apply_valid_only and valid_tweens:
            print(f"\nApplying {len(valid_tweens)} valid meshes...")
            results = self.tween_applicator.apply_tweens(
                valid_tweens, validate_topology=False
            )
            applied_count = sum(1 for _, success in results if success)
            print(f"Successfully applied {applied_count} valid meshes")

        # Delete invalid meshes
        if delete_mismatched and invalid_tweens:
            print(f"\nDeleting {len(invalid_tweens)} mismatched meshes...")
            deleted_count = 0

            for tween in invalid_tweens:
                try:
                    mesh_name = tween.mesh.name()
                    pm.delete(tween.mesh)
                    print(f"  Deleted: {mesh_name}")
                    deleted_count += 1
                except Exception as e:
                    print(f"  Failed to delete {tween.mesh.name()}: {e}")

            # Clean up empty groups
            for group_name in Targets.DEFAULT_GROUPS:
                if pm.objExists(group_name):
                    group = pm.PyNode(group_name)
                    children = pm.listRelatives(group, children=True) or []
                    if not children:
                        try:
                            pm.delete(group)
                            print(f"  Deleted empty group: {group_name}")
                        except:
                            pass

            print(f"Deleted {deleted_count} mismatched meshes")

        # Handle problematic target mesh
        if target_topology_mismatch and delete_mismatched:
            self._cleanup_target_mesh()

        # Summary
        remaining_tweens = Targets.find_all_targets()
        print(f"\nCleanup complete:")
        print(f"  Remaining in-between meshes: {len(remaining_tweens)}")
        print(f"  Applied valid meshes: {len(valid_tweens) if apply_valid_only else 0}")
        if target_topology_mismatch and delete_mismatched:
            print(f"  Target mesh: Updated/cleaned")

        if remaining_tweens:
            print("  All remaining meshes have correct topology")

        return True

    def _cleanup_target_mesh(self):
        """Handle problematic target mesh by hiding it and updating reference."""
        try:
            old_target_name = self.target_mesh.name()

            # Hide the old target instead of deleting (safer)
            pm.setAttr(f"{self.target_mesh}.visibility", False)
            print(f"  Hidden problematic target mesh: {old_target_name}")

            # Update target reference to None (blendShape will still work)
            self.target_mesh = None
            print(f"  Updated target reference to None")

        except Exception as e:
            print(f"  Warning: Could not clean up target mesh: {e}")

    def remove_target_for_export(self):
        """Remove target mesh for clean export - only base mesh with blendShape animation remains."""
        print("=== REMOVING TARGET MESH FOR EXPORT ===")

        if not self._validate_setup():
            return False

        # Check if target mesh exists and remove it
        if self.target_mesh and pm.objExists(self.target_mesh):
            try:
                target_name = self.target_mesh.name()
                pm.delete(self.target_mesh)
                print(f"Removed target mesh: {target_name}")
                self.target_mesh = None

                # Verify blendShape still works
                if self.blendshape and pm.objExists(self.blendshape):
                    print(f"BlendShape {self.blendshape} preserved - animation intact")
                else:
                    print("WARNING: BlendShape not found - animation may be lost")

                print(
                    "Export cleanup complete - scene contains only base mesh with animation"
                )
                return True

            except Exception as e:
                print(f"ERROR: Failed to remove target mesh: {e}")
                return False
        else:
            print("No target mesh to remove - scene already clean for export")
            return True

    @classmethod
    def recover_setup(cls, base_mesh=None, target_mesh=None):
        """Recover corrupted blendShape setup."""
        print("=== RECOVERY MODE ===")

        # Use provided objects or fallback to selection
        if base_mesh is None or target_mesh is None:
            selection = pm.selected()
            if len(selection) >= 2:
                base_mesh = selection[0] if base_mesh is None else base_mesh
                target_mesh = selection[1] if target_mesh is None else target_mesh
            else:
                print("Need base_mesh and target_mesh parameters or select 2 meshes")
                return None

        # Use recovery utility
        success = Recovery.recover_with_targets(base_mesh, target_mesh)

        if success:
            print("Recovery complete! Creating new animator...")
            # Return new animator for the recovered setup
            return cls.from_existing(base_mesh)
        else:
            print("Recovery failed. Check the console for details.")
            return None


class Recovery:
    """Utilities for recovering from corrupted blendShape setups."""

    @staticmethod
    def fix_corrupted_animation(base_mesh: pm.PyNode, target_mesh: pm.PyNode) -> bool:
        """Rebuild corrupted blendShape animation."""
        print("=== RECOVERY: Fixing corrupted animation ===")

        history = base_mesh.listHistory(type="blendShape")
        if not history:
            print("No blendShape found to fix")
            return False

        old_blendshape = history[0]

        # Save keyframes
        keyframes = []
        try:
            times = pm.keyframe(
                f"{old_blendshape}.weight[0]", query=True, timeChange=True
            )
            values = pm.keyframe(
                f"{old_blendshape}.weight[0]", query=True, valueChange=True
            )
            if times and values:
                keyframes = list(zip(times, values))
                print(f"  Saved {len(keyframes)} keyframes")
        except:
            print("No keyframes found to preserve")

        # Delete corrupted blendShape
        pm.delete(old_blendshape)
        print("Removed corrupted blendShape")

        # Create fresh blendShape
        new_name = f"{base_mesh.name()}_BS_fixed"
        new_blendshape = pm.blendShape(
            target_mesh, base_mesh, name=new_name, frontOfChain=True, origin="world"
        )[0]
        print(f"Created fresh blendShape: {new_blendshape}")

        # Restore keyframes
        if keyframes:
            for time_val, weight_val in keyframes:
                pm.setKeyframe(
                    new_blendshape,
                    attribute="weight[0]",
                    time=time_val,
                    value=weight_val,
                )

            # Set linear tangents
            start_time, end_time = keyframes[0][0], keyframes[-1][0]
            pm.keyTangent(
                new_blendshape,
                attribute="weight[0]",
                time=(start_time, end_time),
                inTangentType="linear",
                outTangentType="linear",
            )

            print(f"Restored {len(keyframes)} keyframes with linear tangents")

        print("Animation fixed! Test by scrubbing timeline.")
        return True

    @staticmethod
    def recover_with_targets(base_mesh: pm.PyNode, target_mesh: pm.PyNode) -> bool:
        """Complete recovery: fix animation AND restore tween customizations."""
        print("=== COMPLETE RECOVERY ===")

        # Step 1: Fix basic animation
        if not Recovery.fix_corrupted_animation(base_mesh, target_mesh):
            return False

        # Step 2: Update tween references and apply
        history = base_mesh.listHistory(type="blendShape")
        if history:
            new_blendshape = history[0]
            count = Targets.update_all_references(new_blendshape, base_mesh)

            if count > 0:
                # Create temporary animator to apply tweens
                animator = Keyframes(base_mesh, target_mesh, new_blendshape)
                applicator = Applicator(animator)
                results = applicator.apply_tweens()

                successful = sum(1 for _, success in results if success)
                print(f"\n✓ Complete recovery successful!")
                print(f"✓ Basic animation: Working")
                print(f"✓ Tween customizations: {successful} applied")
                return True

        print("Basic animation fixed, but no tweens found to restore")
        return False


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    # Example workflow:
    selection = pm.selected()

    if len(selection) < 1:
        print("ERROR: Please select at least 1 mesh object")
    elif len(selection) == 1:
        # Single selection - load existing setup
        base = selection[0]
        animator = Animator.from_existing(base)
        if animator:
            # Add additional in-betweens
            current_time = pm.currentTime(query=True)
            # new_tweens = animator.edit(mode="frames", target_frame=current_time)
            # Custom cleanup
            # animator.diagnose_topology_issues()

            # # 1. Apply good edits without deleting anything
            # animator.cleanup_topology_mismatches(delete_mismatched=False)
            # # 2. If satisfied, then clean up the bad meshes
            # animator.cleanup_topology_mismatches(
            #     apply_valid_only=False, delete_mismatched=True
            # )

            animator.remove_target_for_export()

# animator.finalize_for_export(
#     cleanup_scene=False,  # Don't clean up yet
#     delete_inbetween_meshes=False,  # Keep them for safety
#     delete_construction_history=False,  # Keep history
# )
# else:2
#     # Multiple selections - create new setupW
#     base, target, *inbetween = selection

#     # Option 1: Basic workflow with existing in-betweens
#     if inbetween:
#         animator = Animator.basic_workflow(
#             base, target, inbetween_meshes=inbetween, frame_range=(5500, 5800)
#         )
#     else:2
#         # Option 2: Basic workflow that creates new in-betweens
#         animator = Animator.basic_workflow(base, target, frame_range=(5500, 5800))

# Edit target meshes in Maya
# animator.apply_all_edits()


# -----------------------------------------------------------------------------
# Notes
# -----------------------------------------------------------------------------
