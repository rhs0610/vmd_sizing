# -*- coding: utf-8 -*-
#
import os
import sys
import argparse
import numpy as np

from module.MMath import MRect, MVector2D, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from module.MParams import BoneLinks # noqa
from mmd.PmxData import PmxModel, Bone, Vertex, Material, Morph, DisplaySlot, RigidBody, Joint # noqa
from mmd.VmdData import VmdMotion, VmdBoneFrame, VmdCameraFrame, VmdInfoIk, VmdLightFrame, VmdMorphFrame, VmdShadowFrame, VmdShowIkFrame # noqa
from mmd.PmxReader import PmxReader
from mmd.VmdReader import VmdReader
from mmd.VpdReader import VpdReader
from utils import MFileUtils
from utils.MException import SizingException
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)



cdef class MLegProcessOptions():
    def __init__(self, move_correction_ratio=1, leg_offsets={0: 0}):
        self.move_correction_ratio = move_correction_ratio
        self.leg_offsets = leg_offsets

cdef class MOptions():

    def __init__(self, version_name, logging_level, max_workers, data_set_list, arm_options, \
                 camera_motion, camera_output_vmd_path, is_sizing_camera_only, camera_length, monitor, \
                 is_file, outout_datetime, total_process, now_process, total_process_ctrl, now_process_ctrl, tree_process_dict, leg_options=MLegProcessOptions()):
        self.version_name = version_name
        self.logging_level = logging_level
        self.max_workers = max_workers
        self.data_set_list = data_set_list
        self.arm_options = arm_options
        self.camera_motion = camera_motion
        self.camera_output_vmd_path = camera_output_vmd_path
        self.is_sizing_camera_only = is_sizing_camera_only
        self.camera_length = camera_length
        self.monitor = monitor
        self.is_file = is_file
        self.outout_datetime = outout_datetime
        self.total_process = total_process
        self.now_process = now_process
        self.total_process_ctrl = total_process_ctrl
        self.now_process_ctrl = now_process_ctrl
        self.tree_process_dict = tree_process_dict
        self.leg_options = leg_options

    # 複数件の파일セットの足IKの比率を再設定する
    def calc_leg_ratio(self):
        # まず一番小さいXZ比率と一番大きいXZ比率を取得する
        min_xz_ratio = 99999999999
        max_xz_ratio = -99999999999
        min_heads_tall_ratio = 99999999999
        max_heads_tall_ratio = -99999999999

        xz_ratios = []
        for data_set_idx, data_set in enumerate(self.data_set_list):
            xz_ratios.append(data_set.original_xz_ratio)

        # XZ比率の差(差分の1.2倍をリミットとする)
        total_xz_ratio = min(np.mean(xz_ratios), 1.2) * self.leg_options.move_correction_ratio
        logger.test("total_xz_ratio: %s", total_xz_ratio)

        log_txt = "\n다리 길이의 비율 ---------\n"
        log_txt = f"{log_txt}전체 이동량 보정： {round(self.leg_options.move_correction_ratio, 5)}\n"

        for data_set_idx, data_set in enumerate(self.data_set_list):
            if len(self.data_set_list) > 1:
                # XZ比率は合計から導き出した比率(頭身比率を加味する)
                data_set.xz_ratio = total_xz_ratio
                data_set.y_ratio = data_set.original_y_ratio
            else:
                # セットが1件（一人모션の場合はそのままで보정値だけかける）
                data_set.xz_ratio = data_set.original_xz_ratio * self.leg_options.move_correction_ratio
                data_set.y_ratio = data_set.original_y_ratio

            log_txt = "{0}　【No.{1}】　xz: {2}, y: {3}, (元: xz: {4})\n".format(log_txt, (data_set_idx + 1), round(data_set.xz_ratio, 5), round(data_set.y_ratio, 5), round(data_set.original_xz_ratio, 5))

        logger.info(log_txt)

    @classmethod
    def parse(cls, version_name: str):
        return c_parse(version_name)

cdef c_parse(str version_name):
    parser = argparse.ArgumentParser()
    parser.add_argument("--motion_path", required=True, type=(lambda x: list(map(str, x.split(';')))))
    parser.add_argument("--org_model_path", required=True, type=(lambda x: list(map(str, x.split(';')))))
    parser.add_argument("--rep_model_path", required=True, type=(lambda x: list(map(str, x.split(';')))))
    parser.add_argument("--detail_stance_flg", required=True, type=(lambda x: list(map(int, x.split(';')))))
    parser.add_argument("--twist_flg", required=True, type=(lambda x: list(map(int, x.split(';')))))
    parser.add_argument("--arm_process_flg_avoidance", type=int, default=0)
    parser.add_argument("--avoidance_target_list", default=[], type=(lambda x: list(map(str, x.split(';')))))
    parser.add_argument("--arm_process_flg_alignment", type=int, default=0)
    parser.add_argument("--alignment_finger_flg", type=int, default=0)
    parser.add_argument("--alignment_floor_flg", type=int, default=0)
    parser.add_argument("--alignment_distance_wrist", type=float, default=1.7)
    parser.add_argument("--alignment_distance_finger", type=float, default=1.4)
    parser.add_argument("--alignment_distance_floor", type=float, default=1.8)
    parser.add_argument("--arm_check_skip_flg", type=int, default=0)
    parser.add_argument("--camera_motion_path", type=str, default="")
    parser.add_argument("--camera_org_model_path", default=[], type=(lambda x: list(map(str, x.split(';')))))
    parser.add_argument("--camera_offset_y", default=[], type=(lambda x: list(map(str, x.split(';')))))
    parser.add_argument("--verbose", type=int, default=20)

    args = parser.parse_args()

    # ログディレクトリ作成
    os.makedirs("log", exist_ok=True)

    MLogger.initialize(level=args.verbose, is_file=True)

    try:
        arm_process_flg_avoidance = True if args.arm_process_flg_avoidance == 1 else False
        arm_process_flg_alignment = True if args.arm_process_flg_alignment == 1 else False
        alignment_finger_flg = True if args.alignment_finger_flg == 1 else False
        alignment_floor_flg = True if args.alignment_floor_flg == 1 else False
        arm_check_skip_flg = True if args.arm_check_skip_flg == 1 else False

        arm_options = MArmProcessOptions(
            arm_process_flg_avoidance, \
            {0: [(a.strip() if len(a.strip()) > 0 else "") for a in args.avoidance_target_list]}, \
            arm_process_flg_alignment, \
            alignment_finger_flg, \
            alignment_floor_flg, \
            args.alignment_distance_wrist, \
            args.alignment_distance_finger, \
            args.alignment_distance_floor, \
            arm_check_skip_flg
        )

        # 元모델が未指定の場合、空で処理する
        if not args.camera_org_model_path or (len(args.camera_org_model_path) == 1 and len(args.camera_org_model_path[0]) == 0):
            args.camera_org_model_path = []
            for org_path in args.org_model_path:
                args.camera_org_model_path.append("")

        # オフセットYが未指定の場合、0で処理する
        if not args.camera_offset_y or (len(args.camera_offset_y) == 1 and len(args.camera_offset_y[0]) == 0):
            args.camera_offset_y = []
            for org_path in args.org_model_path:
                args.camera_offset_y.append(0)

        data_set_list = []
        for set_no, (motion_path, org_model_path, rep_model_path, detail_stance_flg_val, twist_flg_val, camera_org_model_path, camera_offset_y) in enumerate( \
            zip(args.motion_path, args.org_model_path, args.rep_model_path, args.detail_stance_flg, args.twist_flg, args.camera_org_model_path, \
                args.camera_offset_y)): # noqa

            display_set_no = "【No.{0}】".format(set_no + 1)

            # 모션パス --------
            logger.info("%s 조정 대상 모션 VMD/VPD 파일 가져오기 시작", display_set_no)

            file_name, input_ext = os.path.splitext(os.path.basename(motion_path))
            if input_ext.lower() == ".vmd":
                motion_reader = VmdReader(motion_path)
            elif input_ext.lower() == ".vpd":
                motion_reader = VpdReader(motion_path)
            else:
                raise SizingException("{0}.motion_path 읽기 실패(확장자 부정확): {1}".format(display_set_no, os.path.basename(motion_path)))

            motion = motion_reader.read_data()

            logger.info("%s 조정 대상 모션 VMD/VPD 파일 읽기 성공 %s", display_set_no, os.path.basename(motion_path))

            # 元모델 ----------
            logger.info("%s 모션 생성 원본 모델 PMX 파일 읽기 시작", display_set_no)

            file_name, input_ext = os.path.splitext(os.path.basename(org_model_path))
            if input_ext.lower() == ".pmx":
                org_model_reader = PmxReader(org_model_path)
            else:
                raise SizingException("{0}.org_model_path 읽기 실패(확장자 부정확): {1}".format(display_set_no, os.path.basename(org_model_path)))

            org_model = org_model_reader.read_data()

            logger.info("%s 모션 작성 원본 모델 PMX 파일 읽기 성공 %s", display_set_no, os.path.basename(org_model_path))

            # 先모델 ----------
            logger.info("%s 모션 변환용 모델 PMX 파일 읽기 시작", display_set_no)

            file_name, input_ext = os.path.splitext(os.path.basename(rep_model_path))
            if input_ext.lower() == ".pmx":
                rep_model_reader = PmxReader(rep_model_path)
            else:
                raise SizingException("{0}.rep_model_path 읽기 실패 (확장자 부정확): {1}".format(display_set_no, os.path.basename(rep_model_path)))

            rep_model = rep_model_reader.read_data()

            logger.info("%s 모션 변환용 모델 PMX파일 읽기 성공 %s", display_set_no, os.path.basename(rep_model_path))

            # 元모델 ----------
            if len(camera_org_model_path) > 0:
                logger.info("%s 카메라 작성 원본 모델PMX 파일 읽기 시작", display_set_no)

                file_name, input_ext = os.path.splitext(os.path.basename(camera_org_model_path))
                if input_ext.lower() == ".pmx":
                    camera_org_model_reader = PmxReader(camera_org_model_path)
                else:
                    raise SizingException("{0}.camera_org_model_path 읽기 실패(확장자 부정확): {1}".format(display_set_no, os.path.basename(camera_org_model_path)))

                camera_org_model = camera_org_model_reader.read_data()

                logger.info("%s 카메라 작성 원본 모델 PMX파일 읽기 성공 %s", display_set_no, os.path.basename(camera_org_model_path))
            else:
                # 카메라元모델が未指定の場合、작성 원본 모델をそのまま流用
                camera_org_model = org_model

            detail_stance_flg = True if detail_stance_flg_val == 1 else False
            twist_flg = True if twist_flg_val == 1 else False

            # 出力파일パス
            output_vmd_path = MFileUtils.get_output_vmd_path(motion_path, rep_model_path, detail_stance_flg, twist_flg, arm_process_flg_avoidance, arm_process_flg_alignment, False, "", True)

            data_set = MOptionsDataSet(
                motion,
                org_model,
                rep_model,
                output_vmd_path,
                detail_stance_flg,
                twist_flg,
                [],
                camera_org_model,
                camera_offset_y,
                ["센터 XZ 보정", "상반신 보정", "하반신 보정", "발 IK 보정", "발끝 보정", "발끝 IK 보정", "어깨 보정", "센터 Y 보정"]
            )

            data_set_list.append(data_set)

        if len(args.camera_motion_path) != 0:
            # 카메라パス --------
            logger.info("조정 대상 카메라 VMD 파일 읽기 시작")

            file_name, input_ext = os.path.splitext(os.path.basename(args.camera_motion_path))
            if input_ext.lower() == ".vmd":
                camera_motion_reader = VmdReader(args.camera_motion_path)
            else:
                raise SizingException("camera_motion_path 읽기 실패(확장자 부정확): %s", os.path.basename(args.camera_motion_path))

            camera_motion = camera_motion_reader.read_data()
            camera_output_vmd_path = MFileUtils.get_output_camera_vmd_path(args.camera_motion_path, data_set_list[0].rep_model.path, "")

            logger.info("조정 대상 카메라 VMD/VPD파일 읽기 성공 %s", os.path.basename(args.camera_motion_path))
        else:
            camera_motion = None
            camera_output_vmd_path = None

        options = MOptions(\
            version_name=version_name, \
            logging_level=args.verbose, \
            data_set_list=data_set_list, \
            arm_options=arm_options, \
            camera_motion=camera_motion, \
            camera_output_vmd_path=camera_output_vmd_path, \
            monitor=sys.stdout, \
            is_file=True, \
            outout_datetime=logger.outout_datetime, \
            max_workers=1, \
            total_process=0, \
            now_process=0, \
            total_process_ctrl=None, \
            now_process_ctrl=None, \
            tree_process_dict={})

        return options
    except SizingException as se:
        logger.error("사이징 처리가 처리할수 없는 데이터로 종료되었습니다.\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
    except Exception as e:
        logger.critical("사이징 처리가 의도치 않은 오류로 종료되었습니다.", e, decoration=MLogger.DECORATION_BOX)


cdef class MOptionsDataSet():

    def __init__(self, motion, org_model=None, rep_model=None, output_vmd_path=None, detail_stance_flg=0, twist_flg=0, morph_list=[], \
                 camera_org_model=None, camera_offset_y=0, selected_stance_details=[]):
        self.motion = motion
        self.org_model = org_model
        self.rep_model = rep_model
        self.output_vmd_path = output_vmd_path
        self.detail_stance_flg = detail_stance_flg
        self.twist_flg = twist_flg
        self.morph_list = morph_list
        self.camera_org_model = camera_org_model
        self.camera_offset_y = camera_offset_y
        self.selected_stance_details = selected_stance_details

        self.org_motion = self.motion.copy()
        self.test_params = None
        self.full_arms = False

        # 本来の足IKの比率
        self.original_xz_ratio = 1
        self.original_y_ratio = 1
        self.original_heads_tall_ratio = 1

        # 実際に計算に使う足IKの比率
        self.xz_ratio = 1
        self.y_ratio = 1


cdef class MArmProcessOptions():

    def __init__(self, avoidance: bool, avoidance_target_list: dict, alignment: bool, alignment_finger_flg: bool, alignment_floor_flg: bool, \
                 alignment_distance_wrist: float, alignment_distance_finger: float, alignment_distance_floor: float, arm_check_skip_flg: bool):
        self.avoidance = avoidance
        self.avoidance_target_list = avoidance_target_list
        self.alignment = alignment
        self.alignment_finger_flg = alignment_finger_flg
        self.alignment_floor_flg = alignment_floor_flg
        self.alignment_distance_wrist = alignment_distance_wrist
        self.alignment_distance_finger = alignment_distance_finger
        self.alignment_distance_floor = alignment_distance_floor
        self.arm_check_skip_flg = arm_check_skip_flg

class MCsvOptions():

    def __init__(self, version_name, logging_level, motion):
        self.version_name = version_name
        self.logging_level = logging_level
        self.motion = motion


class MVmdOptions():

    def __init__(self, version_name, logging_level, bone_csv_path, morph_csv_path, camera_csv_path):
        self.version_name = version_name
        self.logging_level = logging_level
        self.bone_csv_path = bone_csv_path
        self.morph_csv_path = morph_csv_path
        self.camera_csv_path = camera_csv_path

