from __future__ import annotations
from typing import Dict, List, Tuple, Optional, Union
import pymel.core as pm
from pymel.core.general import PyNode
from pymel.core import datatypes as dt

import pythontk as ptk


NodeLike = Union[str, PyNode]


class HoseRig(ptk.LoggingMixin):
    """
    Build a spline-IK hose that exports cleanly to Unity (bake joints for export).
    - Joints along (a duplicated, optionally rebuilt) centerline curve
    - Spline IK with Advanced Twist using start/end locators
    - Arc-length based stretch (+ optional volume preservation)
    - Non-destructive: original curve and mesh untouched

    RECENT IMPROVEMENTS:
    - ✅ Cluster-based CV control (more stable than direct component connections)
    - ✅ Correct segmentScaleCompensate=False for proper stretch behavior
    - ✅ Simplified inverse-sqrt volume preservation (single node vs 3 nodes)
    - ✅ Clean arc-length setup (no unnecessary disconnects)
    - ✅ Optional auto-anchor end controls to start/end locators
    """

    def __init__(
        self,
        hose_mesh: NodeLike,
        centerline_curve: NodeLike,
        start_locator: NodeLike,
        end_locator: NodeLike,
        name: str = "hose",
        joint_count: int = 12,
        rebuild_curve: bool = True,
        curve_degree: int = 3,
        preserve_volume: bool = True,
        primary_axis: str = "x",  # joint aim
        up_axis: str = "y",  # object up for Advanced Twist
        auto_anchor_ends: bool = False,  # Auto-anchor first/last CV controls to locators
        log_level: str = "WARNING",
    ) -> None:
        super().__init__()
        self.logger.setLevel(log_level)

        # Inputs
        self.mesh: PyNode = pm.PyNode(hose_mesh)
        self.src_curve: PyNode = pm.PyNode(centerline_curve)
        self.loc_start: PyNode = pm.PyNode(start_locator)
        self.loc_end: PyNode = pm.PyNode(end_locator)

        # Config
        self.name = name
        self.joint_count = max(2, int(joint_count))
        self.rebuild_curve = rebuild_curve
        self.curve_degree = int(curve_degree)
        self.preserve_volume = bool(preserve_volume)
        self.primary_axis = primary_axis.lower()
        self.up_axis = up_axis.lower()
        self.auto_anchor_ends = bool(auto_anchor_ends)

        # Products
        self.grp_rig: Optional[PyNode] = None
        self.grp_skel: Optional[PyNode] = None
        self.grp_util: Optional[PyNode] = None
        self.grp_ctrl: Optional[PyNode] = None
        self.grp_cv_ctrls: Optional[PyNode] = None
        self.joints: List[PyNode] = []
        self.ik_handle: Optional[PyNode] = None
        self.ik_effector: Optional[PyNode] = None
        self.ik_curve: Optional[PyNode] = None
        self.curve_info: Optional[PyNode] = None
        self.rest_length: Optional[float] = None
        self.skin_cluster: Optional[PyNode] = None
        self.control_curves: List[PyNode] = []
        self.main_ctrl: Optional[PyNode] = None
        self.cv_controls: List[PyNode] = []
        self._cv_clusters: List[Tuple[PyNode, PyNode]] = []  # (handle, cluster) pairs
        self.stretch_multiplier_node: Optional[PyNode] = None
        self.volume_blend_node: Optional[PyNode] = None
        self.export_joints: List[PyNode] = []  # Clean joints for Unity export
        self.ctrl_constraints: List[PyNode] = []  # Track constraints for baking

    # -------------------------
    # Public API
    # -------------------------
    def build(self) -> Dict[str, PyNode]:
        """Build the complete rig. Returns created nodes."""
        self._validate_inputs()
        self._build_groups()
        self._prepare_curve()
        self._build_joint_chain()
        self._setup_spline_ik()
        self._setup_stretch_and_volume()
        self._create_control_system()
        self._create_unity_export_setup()
        self._skin_mesh()

        return {
            "rig_group": self.grp_rig,
            "skeleton_group": self.grp_skel,
            "utility_group": self.grp_util,
            "control_group": self.grp_ctrl,
            "joints_root": self.joints[0],
            "joints": pm.sets(
                self.joints, name=f"{self.name}_joints_SET"
            ),  # convenience
            "ik_handle": self.ik_handle,
            "ik_curve": self.ik_curve,
            "skin_cluster": self.skin_cluster,
            "main_control": self.main_ctrl,
            "cv_controls": self.cv_controls,
            "export_joints": self.export_joints,
        }

    # -------------------------
    # Core steps
    # -------------------------
    def _validate_inputs(self) -> None:
        if not self.mesh.getShapes():
            raise ValueError("Hose mesh has no shape.")
        if self.src_curve.getShape().nodeType() not in ("nurbsCurve",):
            raise TypeError("Centerline must be a NURBS curve.")
        if self.loc_start.nodeType() not in ("transform",):
            raise TypeError("Start locator must be a transform.")
        if self.loc_end.nodeType() not in ("transform",):
            raise TypeError("End locator must be a transform.")

    def _build_groups(self) -> None:
        self.grp_rig = pm.group(empty=True, name=f"{self.name}_RIG_GRP")
        self.grp_skel = pm.group(
            empty=True, name=f"{self.name}_SKEL_GRP", parent=self.grp_rig
        )
        self.grp_util = pm.group(
            empty=True, name=f"{self.name}_UTIL_GRP", parent=self.grp_rig
        )
        self.grp_ctrl = pm.group(
            empty=True, name=f"{self.name}_CTRL_GRP", parent=self.grp_rig
        )
        self.grp_cv_ctrls = pm.group(
            empty=True, name=f"{self.name}_CV_CTRL_GRP", parent=self.grp_ctrl
        )

    def _prepare_curve(self) -> None:
        """Duplicate (and optionally rebuild) the centerline for the IK; keep original intact."""
        dup = pm.duplicate(self.src_curve, name=f"{self.name}_IK_CRV")[0]
        if self.rebuild_curve:
            # Uniform parameterization helps distribute joints nicely.
            pm.rebuildCurve(
                dup,
                rebuildType=0,
                endKnots=True,
                keepEndPoints=True,
                keepTangents=False,
                spans=max(1, self.joint_count - 1),
                degree=self.curve_degree,
                fitRebuild=True,
                tolerance=0.001,
                constructionHistory=True,
            )
        self.ik_curve = dup
        pm.parent(self.ik_curve, self.grp_util)

        # Clean, stable arc-length setup (no stray disconnects)
        self.curve_info = pm.createNode("curveInfo", name=f"{self.name}_curveInfo")
        self.ik_curve.getShape().worldSpace[0] >> self.curve_info.inputCurve
        self.rest_length = float(self.curve_info.arcLength.get())

    def _build_joint_chain(self) -> None:
        """Evenly sample the curve and create a joint per sample; orient along the chain."""
        params = self._even_params(self.joint_count)
        positions = [self._point_on_curve(self.ik_curve, u) for u in params]

        parent: Optional[PyNode] = None
        self.joints = []
        for i, pos in enumerate(positions):
            j = pm.createNode("joint", name=f"{self.name}_JNT_{i+1:02d}")
            j.translate.set(pos)
            j.radius.set(0.5)
            if parent:
                pm.parent(j, parent)
                # For proper stretch behavior: set segmentScaleCompensate = False on child joints
                if j.hasAttr("segmentScaleCompensate"):
                    j.segmentScaleCompensate.set(False)
            else:
                pm.parent(j, self.grp_skel)
            parent = j
            self.joints.append(j)

        # Orient joints down the chain: aim primary axis forward, secondary up axis
        primary, secondary = self._axis_flags(self.primary_axis, self.up_axis)
        pm.joint(
            self.joints[0],
            edit=True,
            orientJoint=primary,  # 'xyz' etc.
            secondaryAxisOrient=secondary,  # 'yup', 'zup', ...
            zeroScaleOrient=True,
            children=True,
        )
        # Freeze rotations on root only (preserve jointOrient down the chain)
        pm.makeIdentity(
            self.joints[0], apply=True, rotate=True, translate=False, scale=False
        )

    def _setup_spline_ik(self) -> None:
        """Create spline IK using the prepared curve; enable Advanced Twist via locators."""
        ikh, eff = pm.ikHandle(
            startJoint=self.joints[0],
            endEffector=self.joints[-1],
            curve=self.ik_curve,
            createCurve=False,
            parentCurve=False,
            solver="ikSplineSolver",
            name=f"{self.name}_IKH",
        )
        self.ik_handle, self.ik_effector = ikh, eff
        pm.parent(self.ik_handle, self.grp_util)

        # Advanced Twist setup
        self.ik_handle.dTwistControlEnable.set(True)
        self.ik_handle.dWorldUpType.set(4)  # Object Rotation Up (Start/End)
        self.ik_handle.dForwardAxis.set(self._axis_enum(self.primary_axis))
        self.ik_handle.dWorldUpAxis.set(self._axis_enum(self.up_axis))
        self.loc_start.worldMatrix[0] >> self.ik_handle.dWorldUpMatrix
        self.loc_end.worldMatrix[0] >> self.ik_handle.dWorldUpMatrixEnd
        # Up vectors consistent with selected up axis
        up_vec = self._axis_vector(self.up_axis)
        self.ik_handle.dWorldUpVector.set(up_vec)
        self.ik_handle.dWorldUpVectorEnd.set(up_vec)

    def _setup_stretch_and_volume(self) -> None:
        """Drive per-segment scale with arc-length ratio (plus optional volume preservation)."""
        if not self.curve_info or self.rest_length is None:
            raise RuntimeError("Curve info not initialized.")

        # ratio = currentLength / restLength
        md_ratio = pm.createNode("multiplyDivide", name=f"{self.name}_md_ratio")
        md_ratio.operation.set(2)  # divide
        self.curve_info.arcLength >> md_ratio.input1X
        md_ratio.input2X.set(max(self.rest_length, 1e-8))

        # Drive primary-axis scale on each joint
        for j in self.joints:
            if self.primary_axis == "x":
                md_ratio.outputX >> j.scaleX
            elif self.primary_axis == "y":
                md_ratio.outputX >> j.scaleY
            else:
                md_ratio.outputX >> j.scaleZ

        if self.preserve_volume:
            # Simpler, numerically stable inverse-sqrt volume preservation
            # invSqrt = ratio ** -0.5  (stable and compact)
            md_inv_sqrt = pm.createNode(
                "multiplyDivide", name=f"{self.name}_md_invsqrt"
            )
            md_inv_sqrt.operation.set(3)  # power
            md_ratio.outputX >> md_inv_sqrt.input1X
            md_inv_sqrt.input2X.set(-0.5)

            for j in self.joints:
                if self.primary_axis == "x":
                    md_inv_sqrt.outputX >> j.scaleY
                    md_inv_sqrt.outputX >> j.scaleZ
                elif self.primary_axis == "y":
                    md_inv_sqrt.outputX >> j.scaleX
                    md_inv_sqrt.outputX >> j.scaleZ
                else:
                    md_inv_sqrt.outputX >> j.scaleX
                    md_inv_sqrt.outputX >> j.scaleY

    def _skin_mesh(self) -> None:
        """Bind mesh to joints (non-destructive: only if not already skinned)."""
        existing = pm.listHistory(
            self.mesh,
            future=False,
            pruneDagObjects=True,
            interestLevel=2,
            type="skinCluster",
        )
        if existing:
            self.skin_cluster = existing[0]
            self.logger.info("Mesh already skinned; leaving existing skinCluster.")
            # Ensure all joints are influences
            for j in self.joints:
                try:
                    pm.skinCluster(
                        self.skin_cluster, edit=True, addInfluence=j, weight=0.0
                    )
                except RuntimeError:
                    pass
            return

        self.skin_cluster = pm.skinCluster(
            self.joints,
            self.mesh,
            toSelectedBones=True,
            bindMethod=0,  # Closest Distance
            skinMethod=0,  # Classic Linear
            normalizeWeights=1,  # Interactive
            obeyMaxInfluences=True,
            maximumInfluences=4,
            dropoffRate=4.0,
            name=f"{self.name}_SKC",
        )

    def _create_control_system(self) -> None:
        """Create animation controls for the hose rig."""
        self._create_main_control()
        self._create_cv_controls()
        self._connect_curve_controls()
        self._add_control_attributes()

    def _create_main_control(self) -> None:
        """Create the main control with global attributes."""
        # Create a better control shape (square with cross)
        self.main_ctrl = self._create_control_shape(
            name=f"{self.name}_MAIN_CTRL", shape_type="square_cross", size=3.0
        )

        # Position at curve center
        curve_center = self._get_curve_center()
        self.main_ctrl.translate.set(curve_center)

        # Parent to control group
        pm.parent(self.main_ctrl, self.grp_ctrl)

        # Color the control
        self._color_control(self.main_ctrl, color=17)  # Yellow

    def _create_cv_controls(self) -> None:
        """Create controls for each CV of the IK curve."""
        curve_shape = self.ik_curve.getShape()
        cv_count = curve_shape.numCVs()

        self.cv_controls = []

        for i in range(cv_count):
            # Get CV position
            cv_pos = pm.pointPosition(f"{self.ik_curve}.cv[{i}]", world=True)

            # Create control with better shape
            ctrl = self._create_control_shape(
                name=f"{self.name}_CV_{i+1:02d}_CTRL", shape_type="sphere", size=0.8
            )

            # Position control
            ctrl.translate.set(cv_pos)

            # Parent to CV control group
            pm.parent(ctrl, self.grp_cv_ctrls)

            # Color the control based on position
            if i == 0 or i == cv_count - 1:
                self._color_control(ctrl, color=6)  # Blue for ends
            else:
                self._color_control(ctrl, color=13)  # Red for middle

            self.cv_controls.append(ctrl)

    def _create_control_shape(
        self, name: str, shape_type: str = "circle", size: float = 1.0
    ) -> PyNode:
        """Create various control shapes."""
        if shape_type == "circle":
            ctrl = pm.circle(
                name=name, normal=(0, 1, 0), radius=size, constructionHistory=False
            )[0]

        elif shape_type == "square":
            # Create a square control
            points = [
                (-size, 0, -size),
                (size, 0, -size),
                (size, 0, size),
                (-size, 0, size),
                (-size, 0, -size),
            ]
            ctrl = pm.curve(name=name, degree=1, point=points)

        elif shape_type == "square_cross":
            # Create a square with cross
            points = [
                (-size, 0, -size),
                (size, 0, -size),
                (size, 0, size),
                (-size, 0, size),
                (-size, 0, -size),
                (0, 0, -size),
                (0, 0, size),
                (0, 0, 0),
                (-size, 0, 0),
                (size, 0, 0),
            ]
            ctrl = pm.curve(name=name, degree=1, point=points)

        elif shape_type == "sphere":
            # Create a sphere-like control (3 circles)
            circle1 = pm.circle(
                name=f"{name}_temp1",
                normal=(1, 0, 0),
                radius=size,
                constructionHistory=False,
            )[0]
            circle2 = pm.circle(
                name=f"{name}_temp2",
                normal=(0, 1, 0),
                radius=size,
                constructionHistory=False,
            )[0]
            circle3 = pm.circle(
                name=f"{name}_temp3",
                normal=(0, 0, 1),
                radius=size,
                constructionHistory=False,
            )[0]

            # Combine shapes
            pm.parent(circle2.getShape(), circle1, relative=True, shape=True)
            pm.parent(circle3.getShape(), circle1, relative=True, shape=True)
            pm.delete(circle2, circle3)

            ctrl = pm.rename(circle1, name)

        elif shape_type == "cube":
            # Create a cube control
            points = [
                # Bottom face
                (-size, -size, -size),
                (size, -size, -size),
                (size, -size, size),
                (-size, -size, size),
                (-size, -size, -size),
                # Top face
                (-size, size, -size),
                (size, size, -size),
                (size, size, size),
                (-size, size, size),
                (-size, size, -size),
                # Vertical edges
                (-size, -size, -size),
                (-size, size, -size),
                (size, size, -size),
                (size, -size, -size),
                (size, -size, size),
                (size, size, size),
                (-size, size, size),
                (-size, -size, size),
            ]
            ctrl = pm.curve(name=name, degree=1, point=points)

        else:
            # Default to circle
            ctrl = pm.circle(
                name=name, normal=(0, 1, 0), radius=size, constructionHistory=False
            )[0]

        return ctrl

    def _connect_curve_controls(self) -> None:
        """Deform the IK curve via per-CV clusters driven by the CV controls.
        Also optionally anchor first/last controls to start/end locators for intuitive endpoints.
        """
        if not self.cv_controls:
            return

        curve_shape = self.ik_curve.getShape()
        cv_count = curve_shape.numCVs()

        self._cv_clusters = []  # (handle, cluster) pairs

        for i, ctrl in enumerate(self.cv_controls):
            # Create a relative cluster on the CV
            cluster_name = f"{self.name}_CV_{i+1:02d}_CLS"
            try:
                cluster_result = pm.cluster(
                    f"{self.ik_curve}.cv[{i}]",
                    name=cluster_name,
                    relative=True,  # keeps offsets predictable
                    bindState=True,
                )

                # Get the cluster deformer node and its handle
                cluster_deformer = pm.PyNode(
                    cluster_name
                )  # The actual cluster deformer
                cluster_handle = pm.PyNode(
                    f"{cluster_name}Handle"
                )  # The transform handle

                # Keep handle under UTIL and hide it
                pm.parent(cluster_handle, self.grp_util)
                cluster_handle.visibility.set(False)

                # Zero the handle (snap to current CV), then drive via parentConstraint
                pm.delete(pm.pointConstraint(ctrl, cluster_handle))  # snap once
                pm.parentConstraint(ctrl, cluster_handle, maintainOffset=False)

                self._cv_clusters.append((cluster_handle, cluster_deformer))

            except Exception as e:
                self.logger.warning(f"Failed to create cluster for CV {i}: {e}")
                # Fallback to direct connection
                ctrl.translate >> pm.PyNode(f"{self.ik_curve}.cv[{i}]")

        # Optionally make ends follow the locators by default (animator can still move the end controls)
        if self.auto_anchor_ends and len(self.cv_controls) >= 2:
            pm.parentConstraint(
                self.loc_start, self.cv_controls[0], maintainOffset=False
            )
            pm.parentConstraint(
                self.loc_end, self.cv_controls[-1], maintainOffset=False
            )

    def _add_control_attributes(self) -> None:
        """Add custom attributes to the main control."""
        import maya.cmds as cmds

        # Add separator
        pm.addAttr(
            self.main_ctrl,
            longName="HOSE_CONTROLS",
            attributeType="enum",
            enumName="___________:",
            keyable=False,
        )
        cmds.setAttr(f"{self.main_ctrl}.HOSE_CONTROLS", channelBox=True)

        # Stretch multiplier
        pm.addAttr(
            self.main_ctrl,
            longName="stretchMultiplier",
            attributeType="float",
            defaultValue=1.0,
            minValue=0.1,
            maxValue=5.0,
            keyable=True,
        )

        # Stretch enable/disable
        pm.addAttr(
            self.main_ctrl,
            longName="stretchEnable",
            attributeType="bool",
            defaultValue=True,
            keyable=True,
        )

        # Volume preservation toggle
        pm.addAttr(
            self.main_ctrl,
            longName="volumePreservation",
            attributeType="float",
            defaultValue=1.0 if self.preserve_volume else 0.0,
            minValue=0.0,
            maxValue=1.0,
            keyable=True,
        )

        # Twist controls
        pm.addAttr(
            self.main_ctrl,
            longName="globalTwist",
            attributeType="float",
            defaultValue=0.0,
            keyable=True,
        )

        # Auto-anchor end controls (if enabled)
        if self.auto_anchor_ends:
            pm.addAttr(
                self.main_ctrl,
                longName="anchorEndControls",
                attributeType="bool",
                defaultValue=True,
                keyable=False,
            )
            cmds.setAttr(f"{self.main_ctrl}.anchorEndControls", channelBox=True)

        # Visibility controls
        pm.addAttr(
            self.main_ctrl,
            longName="VISIBILITY",
            attributeType="enum",
            enumName="___________:",
            keyable=False,
        )
        cmds.setAttr(f"{self.main_ctrl}.VISIBILITY", channelBox=True)

        pm.addAttr(
            self.main_ctrl,
            longName="showCVControls",
            attributeType="bool",
            defaultValue=True,
            keyable=False,
        )
        cmds.setAttr(f"{self.main_ctrl}.showCVControls", channelBox=True)

        pm.addAttr(
            self.main_ctrl,
            longName="showJoints",
            attributeType="bool",
            defaultValue=False,
            keyable=False,
        )
        cmds.setAttr(f"{self.main_ctrl}.showJoints", channelBox=True)

        # Connect attributes to systems
        self._connect_stretch_control()
        self._connect_volume_control()
        self._connect_twist_controls()
        self._connect_visibility_controls()

    def _connect_stretch_control(self) -> None:
        """Connect the stretch multiplier to the existing stretch system."""
        # Find the stretch ratio multiply divide node
        stretch_nodes = pm.ls(f"{self.name}_md_ratio", type="multiplyDivide")
        if stretch_nodes:
            md_ratio = stretch_nodes[0]

            # Create blend node for stretch enable/disable
            stretch_blend = pm.createNode(
                "blendTwoAttr", name=f"{self.name}_stretch_blend"
            )
            stretch_blend.input[0].set(1.0)  # No stretch value

            # Create multiply node for stretch multiplier
            self.stretch_multiplier_node = pm.createNode(
                "multiplyDivide", name=f"{self.name}_md_stretchCtrl"
            )
            self.stretch_multiplier_node.operation.set(1)  # multiply

            # Connect: ratio * stretchMultiplier
            md_ratio.outputX >> self.stretch_multiplier_node.input1X
            self.main_ctrl.stretchMultiplier >> self.stretch_multiplier_node.input2X

            # Connect to blend node
            self.stretch_multiplier_node.outputX >> stretch_blend.input[1]
            self.main_ctrl.stretchEnable >> stretch_blend.attributesBlender

            # Disconnect original connections and reconnect through blend
            for j in self.joints:
                if self.primary_axis == "x":
                    md_ratio.outputX // j.scaleX  # Disconnect
                    stretch_blend.output >> j.scaleX
                elif self.primary_axis == "y":
                    md_ratio.outputX // j.scaleY
                    stretch_blend.output >> j.scaleY
                else:
                    md_ratio.outputX // j.scaleZ
                    stretch_blend.output >> j.scaleZ

    def _connect_volume_control(self) -> None:
        """Connect volume preservation control to the existing volume system."""
        if self.preserve_volume:
            # Find the inverse volume nodes
            inv_nodes = pm.ls(f"{self.name}_md_invsqrt", type="multiplyDivide")
            if inv_nodes:
                inv_node = inv_nodes[0]

                # Create blend node for volume control
                self.volume_blend_node = pm.createNode(
                    "blendTwoAttr", name=f"{self.name}_volume_blend"
                )
                self.volume_blend_node.input[0].set(1.0)  # No volume preservation

                # Connect inverse volume to blend
                inv_node.outputX >> self.volume_blend_node.input[1]
                (
                    self.main_ctrl.volumePreservation
                    >> self.volume_blend_node.attributesBlender
                )

                # Disconnect and reconnect through blend
                for j in self.joints:
                    if self.primary_axis == "x":
                        inv_node.outputX // j.scaleY
                        inv_node.outputX // j.scaleZ
                        self.volume_blend_node.output >> j.scaleY
                        self.volume_blend_node.output >> j.scaleZ
                    elif self.primary_axis == "y":
                        inv_node.outputX // j.scaleX
                        inv_node.outputX // j.scaleZ
                        self.volume_blend_node.output >> j.scaleX
                        self.volume_blend_node.output >> j.scaleZ
                    else:
                        inv_node.outputX // j.scaleX
                        inv_node.outputX // j.scaleY
                        self.volume_blend_node.output >> j.scaleX
                        self.volume_blend_node.output >> j.scaleY

    def _connect_twist_controls(self) -> None:
        """Connect twist controls to the IK handle."""
        if self.ik_handle:
            # Simple direct connection for global twist
            self.main_ctrl.globalTwist >> self.ik_handle.twist

    def _connect_visibility_controls(self) -> None:
        """Connect visibility controls."""
        # CV Controls visibility
        self.main_ctrl.showCVControls >> self.grp_cv_ctrls.visibility

        # Hide all cluster handles (not clusters) when CV controls are hidden
        for handle, cluster in getattr(self, "_cv_clusters", []):
            self.main_ctrl.showCVControls >> handle.visibility

        # Joint visibility
        self.main_ctrl.showJoints >> self.grp_skel.visibility

    def _get_curve_center(self) -> Tuple[float, float, float]:
        """Get the center point of the curve."""
        start_pos = self._point_on_curve(self.ik_curve, 0.0)
        end_pos = self._point_on_curve(self.ik_curve, 1.0)

        center = (
            (start_pos[0] + end_pos[0]) * 0.5,
            (start_pos[1] + end_pos[1]) * 0.5,
            (start_pos[2] + end_pos[2]) * 0.5,
        )
        return center

    def _color_control(self, control: PyNode, color: int) -> None:
        """Set the display color of a control."""
        shape = control.getShape()
        if shape:
            shape.overrideEnabled.set(True)
            shape.overrideColor.set(color)

    def _create_unity_export_setup(self) -> None:
        """Create clean export joints and setup for Unity."""
        self._create_export_joints()
        self._setup_export_constraints()
        self._add_unity_export_attributes()

    def _create_export_joints(self) -> None:
        """Create clean joints hierarchy for Unity export."""
        # Create export group
        export_grp = pm.group(
            empty=True, name=f"{self.name}_EXPORT_GRP", parent=self.grp_rig
        )

        self.export_joints = []
        parent_joint = None

        for i, rig_joint in enumerate(self.joints):
            # Create clean export joint
            export_joint = pm.createNode(
                "joint", name=f"{self.name}_EXPORT_JNT_{i+1:02d}"
            )

            # Match position and orientation
            export_joint.translate.set(rig_joint.translate.get())
            export_joint.rotate.set(rig_joint.rotate.get())
            export_joint.jointOrient.set(rig_joint.jointOrient.get())
            export_joint.radius.set(0.2)  # Smaller for cleaner look

            # Parent correctly
            if parent_joint:
                pm.parent(export_joint, parent_joint)
            else:
                pm.parent(export_joint, export_grp)

            parent_joint = export_joint
            self.export_joints.append(export_joint)

    def _setup_export_constraints(self) -> None:
        """Constrain export joints to rig joints."""
        for export_joint, rig_joint in zip(self.export_joints, self.joints):
            # Use parent constraint for clean transformation
            constraint = pm.parentConstraint(
                rig_joint, export_joint, maintainOffset=False
            )
            self.ctrl_constraints.append(constraint)

            # Hide constraint from outliner
            constraint.visibility.set(False)

    def _add_unity_export_attributes(self) -> None:
        """Add Unity-specific export controls."""
        import maya.cmds as cmds

        # Add separator for Unity controls
        pm.addAttr(
            self.main_ctrl,
            longName="UNITY_EXPORT",
            attributeType="enum",
            enumName="___________:",
            keyable=False,
        )
        cmds.setAttr(f"{self.main_ctrl}.UNITY_EXPORT", channelBox=True)

        # Export joint visibility
        pm.addAttr(
            self.main_ctrl,
            longName="showExportJoints",
            attributeType="bool",
            defaultValue=True,
            keyable=False,
        )
        cmds.setAttr(f"{self.main_ctrl}.showExportJoints", channelBox=True)

        # Connect export joint visibility
        export_grp = pm.PyNode(f"{self.name}_EXPORT_GRP")
        self.main_ctrl.showExportJoints >> export_grp.visibility

    # -------------------------
    # Unity Export Methods
    # -------------------------
    def bake_animation_for_unity(
        self, start_frame: int = 1, end_frame: int = 100
    ) -> None:
        """Bake animation from rig joints to export joints for Unity."""
        if not self.export_joints:
            self.logger.warning("No export joints found. Run build() first.")
            return

        # Select export joints
        pm.select(self.export_joints)

        # Bake simulation
        pm.bakeResults(
            self.export_joints,
            time=(start_frame, end_frame),
            hierarchy="none",
            sampleBy=1,
            oversamplingRate=1,
            disableImplicitControl=True,
            preserveOutsideKeys=True,
            sparseAnimCurveBake=False,
            removeBakedAttributeFromLayer=False,
            removeBakedAnimFromLayer=False,
            bakeOnOverrideLayer=False,
            minimizeRotation=True,
            controlPoints=False,
            shape=False,
        )

        # Delete constraints after baking
        if self.ctrl_constraints:
            pm.delete(self.ctrl_constraints)
            self.ctrl_constraints.clear()

        self.logger.info(
            f"Animation baked to export joints from frame {start_frame} to {end_frame}"
        )

    def prepare_for_unity_export(self) -> Dict[str, any]:
        """Prepare the rig for Unity export by cleaning up."""
        # Hide rig elements
        self.grp_ctrl.visibility.set(False)
        self.grp_util.visibility.set(False)

        # Show only export joints and mesh
        export_grp = pm.PyNode(f"{self.name}_EXPORT_GRP")
        export_grp.visibility.set(True)

        # Return export information
        return {
            "export_joints": self.export_joints,
            "mesh": self.mesh,
            "export_group": export_grp,
            "joint_count": len(self.export_joints),
            "primary_axis": self.primary_axis,
        }

    def restore_rig_visibility(self) -> None:
        """Restore rig visibility for further editing."""
        self.grp_ctrl.visibility.set(True)
        self.grp_util.visibility.set(True)

    def create_simplified_controls(self) -> List[PyNode]:
        """Create a simplified control setup with fewer controls for easier animation."""
        # Create simplified controls (start, mid, end)
        control_positions = [0.0, 0.5, 1.0]  # Start, middle, end
        simplified_controls = []

        for i, param in enumerate(control_positions):
            pos = self._point_on_curve(self.ik_curve, param)

            # Create larger, more visible control
            ctrl = self._create_control_shape(
                name=f"{self.name}_SIMPLE_{['START', 'MID', 'END'][i]}_CTRL",
                shape_type="cube",
                size=1.5,
            )

            ctrl.translate.set(pos)
            pm.parent(ctrl, self.grp_cv_ctrls)

            # Color code: Blue for ends, Green for middle
            color = 6 if i in [0, 2] else 14  # Blue for ends, Green for middle
            self._color_control(ctrl, color)

            simplified_controls.append(ctrl)

        return simplified_controls

    # -------------------------
    # Utilities
    # -------------------------
    @staticmethod
    def _even_params(count: int) -> List[float]:
        if count == 1:
            return [0.0]
        step = 1.0 / float(count - 1)
        return [i * step for i in range(count)]

    @staticmethod
    def _point_on_curve(curve: PyNode, u: float) -> dt.Point:
        pos = pm.pointOnCurve(curve, parameter=u, turnOnPercentage=True, position=True)
        return dt.Point(pos[0], pos[1], pos[2])

    @staticmethod
    def _axis_enum(axis: str) -> int:
        axis = axis.lower()
        if axis == "x":
            return 0
        if axis == "y":
            return 1
        if axis == "z":
            return 2
        raise ValueError("Axis must be one of: 'x', 'y', 'z'.")

    @staticmethod
    def _axis_vector(axis: str) -> Tuple[float, float, float]:
        axis = axis.lower()
        if axis == "x":
            return (1.0, 0.0, 0.0)
        if axis == "y":
            return (0.0, 1.0, 0.0)
        if axis == "z":
            return (0.0, 0.0, 1.0)
        raise ValueError("Axis must be one of: 'x', 'y', 'z'.")

    @staticmethod
    def _axis_flags(primary: str, up: str) -> Tuple[str, str]:
        """Return orientJoint and secondaryAxisOrient flags."""
        primary_map = {"x": "xyz", "y": "yzx", "z": "zxy"}
        if primary not in primary_map:
            raise ValueError("primary_axis must be 'x', 'y', or 'z'.")
        sec_map = {"x": "xup", "y": "yup", "z": "zup"}
        if up not in sec_map:
            raise ValueError("up_axis must be 'x', 'y', or 'z'.")
        return primary_map[primary], sec_map[up]


if __name__ == "__main__":
    # Unity-optimized settings
    hose_mesh, centerline_curve, start_locator, end_locator = pm.selected()

    # Create the hose rig with Unity-friendly settings
    hose_rig = HoseRig(
        hose_mesh,
        centerline_curve,
        start_locator,
        end_locator,
        "hose_rig",
        joint_count=25,  # Good balance for Unity
        primary_axis="x",  # Unity standard
        preserve_volume=True,
        auto_anchor_ends=False,  # Set to True for automatic end control anchoring
        log_level="INFO",
    )

    # Build the rig
    result = hose_rig.build()

    # Print Unity export instructions
    print("\n" + "=" * 50)
    print("HOSE RIG CREATED FOR UNITY")
    print("=" * 50)
    print(f"Main Control: {result['main_control']}")
    print(f"Export Joints: {len(result['export_joints'])} joints ready for Unity")
    print(f"Mesh: {result['skin_cluster']} (skinned)")
    print("\nUNITY EXPORT WORKFLOW:")
    print("1. Animate using the main control and CV controls")
    print("2. Use 'showExportJoints' to see clean export joints")
    print("3. Call hose_rig.bake_animation_for_unity(1, 100) to bake animation")
    print("4. Call hose_rig.prepare_for_unity_export() to hide rig")
    print("5. Export to FBX with only export joints and mesh visible")
    print("6. Use hose_rig.restore_rig_visibility() to continue editing")

    # Optional: Create simplified controls for easier animation
    # simplified_ctrls = hose_rig.create_simplified_controls()
    # print(f"Simplified Controls: {simplified_ctrls}")

    print("=" * 50)
