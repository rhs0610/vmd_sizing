# -*- coding: utf-8 -*-
#

import logging
import os
from pathlib import Path

from mmd.PmxData import PmxModel
from mmd.VmdWriter import VmdWriter
from mmd.VmdReader import VmdReader
from module.MOptions import MOptions, MOptionsDataSet
from service.parts.MoveService import MoveService
from service.parts.StanceService import StanceService
from service.parts.ArmAlignmentService import ArmAlignmentService
from service.parts.ArmAvoidanceService import ArmAvoidanceService
from service.parts.MorphService import MorphService
from service.parts.CameraService import CameraService
from utils import MServiceUtils
from utils.MException import SizingException, MKilledException
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)


class SizingService():
    def __init__(self, options: MOptions):
        self.options = options

    def execute(self):
        logging.basicConfig(level=self.options.logging_level, format="%(message)s [%(module_name)s]")

        try:
            service_data_txt = "VMD사이징 처리 실행\n------------------------\nexe버전: {version_name}\n".format(version_name=self.options.version_name)

            for data_set_idx, data_set in enumerate(self.options.data_set_list):
                service_data_txt = "{service_data_txt}\n【No.{no}】 --------- \n".format(service_data_txt=service_data_txt, no=(data_set_idx+1)) # noqa
                service_data_txt = "{service_data_txt}　　모션: {motion}\n".format(service_data_txt=service_data_txt,
                                        motion=os.path.basename(data_set.motion.path)) # noqa
                service_data_txt = "{service_data_txt}　　작성 원본 모델: {trace_model} ({model_name})\n".format(service_data_txt=service_data_txt,
                                        trace_model=os.path.basename(data_set.org_model.path), model_name=data_set.org_model.name) # noqa
                service_data_txt = "{service_data_txt}　　변환용 모델: {replace_model} ({model_name})\n".format(service_data_txt=service_data_txt,
                                        replace_model=os.path.basename(data_set.rep_model.path), model_name=data_set.rep_model.name) # noqa
                if data_set.camera_org_model:
                    service_data_txt = "{service_data_txt}　　카메라 작성 원본 모델: {trace_model} ({model_name})\n".format(service_data_txt=service_data_txt,
                                            trace_model=os.path.basename(data_set.camera_org_model.path), model_name=data_set.camera_org_model.name) # noqa
                    service_data_txt = "{service_data_txt}　　Y 오프셋: {camera_offset_y}\n".format(service_data_txt=service_data_txt,
                                            camera_offset_y=data_set.camera_offset_y) # noqa
                service_data_txt = "{service_data_txt}　　자세 추가 보정 유무: {detail_stance_flg}\n".format(service_data_txt=service_data_txt,
                                        detail_stance_flg=data_set.detail_stance_flg) # noqa
                if data_set.detail_stance_flg:
                    # 자세추가보정がある場合、そのリストを表示
                    service_data_txt = "{service_data_txt}　　　　{detail_stance_flg}\n".format(service_data_txt=service_data_txt,
                                            detail_stance_flg=", ".join(data_set.selected_stance_details)) # noqa

                service_data_txt = "{service_data_txt}　　비틀림 분산 유무: {twist_flg}\n".format(service_data_txt=service_data_txt,
                                        twist_flg=data_set.twist_flg) # noqa

                morph_list = []
                for (org_morph_name, rep_morph_name, morph_ratio) in data_set.morph_list:
                    morph_list.append(f"{org_morph_name} → {rep_morph_name} ({morph_ratio})")
                morph_txt = ", ".join(morph_list)
                service_data_txt = "{service_data_txt}　　모프 치환: {morph_txt}\n".format(service_data_txt=service_data_txt,
                                        morph_txt=morph_txt) # noqa

                if data_set_idx in self.options.arm_options.avoidance_target_list:
                    service_data_txt = "{service_data_txt}　　대상 강체명: {avoidance_target}\n".format(service_data_txt=service_data_txt,
                                            avoidance_target=", ".join(self.options.arm_options.avoidance_target_list[data_set_idx])) # noqa

            service_data_txt = "{service_data_txt}\n--------- \n".format(service_data_txt=service_data_txt) # noqa

            if self.options.arm_options.avoidance:
                service_data_txt = "{service_data_txt}강체 접촉 회피: {avoidance}\n".format(service_data_txt=service_data_txt,
                                        avoidance=self.options.arm_options.avoidance) # noqa

            if self.options.arm_options.alignment:
                service_data_txt = "{service_data_txt}손목 위치 맞춤: {alignment} ({distance})\n".format(service_data_txt=service_data_txt,
                                        alignment=self.options.arm_options.alignment, distance=self.options.arm_options.alignment_distance_wrist) # noqa
                service_data_txt = "{service_data_txt}팔 위치 맞춤: {alignment} ({distance})\n".format(service_data_txt=service_data_txt,
                                        alignment=self.options.arm_options.alignment_finger_flg, distance=self.options.arm_options.alignment_distance_finger) # noqa
                service_data_txt = "{service_data_txt}바닥 위치 맞춤: {alignment} ({distance})\n".format(service_data_txt=service_data_txt,
                                        alignment=self.options.arm_options.alignment_floor_flg, distance=self.options.arm_options.alignment_distance_floor) # noqa

            if self.options.arm_options.arm_check_skip_flg:
                service_data_txt = "{service_data_txt}팔 체크 스킵: {arm_check_skip}\n".format(service_data_txt=service_data_txt,
                                        arm_check_skip=self.options.arm_options.arm_check_skip_flg) # noqa

            if self.options.camera_motion:
                service_data_txt = "{service_data_txt}카메라: {camera}({camera_length})\n".format(service_data_txt=service_data_txt,
                                        camera=os.path.basename(self.options.camera_motion.path), camera_length=self.options.camera_length) # noqa
                service_data_txt = "{service_data_txt}　　거리 제한: {camera_length}{camera_length_umlimit}\n".format(service_data_txt=service_data_txt,
                                        camera_length=self.options.camera_length, camera_length_umlimit=("" if self.options.camera_length < 5 else "(무제한)")) # noqa

            service_data_txt = "{service_data_txt}------------------------".format(service_data_txt=service_data_txt) # noqa

            if self.options.total_process_ctrl:
                self.options.total_process_ctrl.write(str(self.options.total_process))
                self.options.now_process_ctrl.write("0")
                self.options.now_process_ctrl.write(str(self.options.now_process))

            logger.info(service_data_txt, decoration=MLogger.DECORATION_BOX)

            if self.options.is_sizing_camera_only is True:
                # 카메라사이징のみ実行する場合、출력結果VMDを読み込む
                for data_set_idx, data_set in enumerate(self.options.data_set_list):
                    reader = VmdReader(data_set.output_vmd_path)
                    data_set.motion = reader.read_data()
            else:
                for data_set_idx, data_set in enumerate(self.options.data_set_list):
                    # 足IKのXYZの比率
                    data_set.original_xz_ratio, data_set.original_y_ratio, data_set.original_heads_tall_ratio = MServiceUtils.calc_leg_ik_ratio(data_set)

                # 足IKの比率再計算
                self.options.calc_leg_ratio()

                # 移動보정
                if not MoveService(self.options).execute():
                    return False

                # 자세보정
                if not StanceService(self.options).execute():
                    return False

                # 강체접촉회피
                if self.options.arm_options.avoidance:
                    if not ArmAvoidanceService(self.options).execute():
                        return False

                # 손목위치맞춤
                if self.options.arm_options.alignment:
                    if not ArmAlignmentService(self.options).execute():
                        return False

            # 카메라보정
            if self.options.camera_motion:
                if not CameraService(self.options).execute():
                    return False

            if self.options.is_sizing_camera_only is False:
                # 모프치환
                if not MorphService(self.options).execute():
                    return False

                for data_set_idx, data_set in enumerate(self.options.data_set_list):
                    # 実行後、출력ファイル存在체크
                    try:
                        # 출력
                        VmdWriter(data_set).write()

                        Path(data_set.output_vmd_path).resolve(True)

                        logger.info("【No.%s】 출력 종료: %s", (data_set_idx + 1), os.path.basename(data_set.output_vmd_path), decoration=MLogger.DECORATION_BOX, title="사이징 성공")
                    except FileNotFoundError as fe:
                        logger.error("【No.%s】출력VMD 파일이 정상적으로 작성되지 않은 것 같습니다.\n 경로를 확인해 주세요.%s\n\n%s", (data_set_idx + 1), data_set.output_vmd_path, fe, decoration=MLogger.DECORATION_BOX)

            if self.options.camera_motion:
                try:
                    camera_model = PmxModel()
                    camera_model.name = "카메라,조명"
                    data_set = MOptionsDataSet(self.options.camera_motion, None, camera_model, self.options.camera_output_vmd_path, 0, 0, [], None, 0, [])
                    # 출력
                    VmdWriter(data_set).write()

                    Path(data_set.output_vmd_path).resolve(True)

                    logger.info("카메라 출력 종료: %s", os.path.basename(data_set.output_vmd_path), decoration=MLogger.DECORATION_BOX, title="사이징 성공")
                except FileNotFoundError as fe:
                    logger.error("카메라 출력 VMD 파일이 정상적으로 작성되지 않은 것 같습니다.\n 경로를 확인해 주세요.%s\n\n%s", self.options.camera_output_vmd_path, fe, decoration=MLogger.DECORATION_BOX)

            if int(self.options.total_process) != int(self.options.now_process):
                logger.warning("일부 처리가 스킵되었습니다.\n화면 좌측 하단의 진척수를 클릭하면, 스킴된 처리가 회색으로 표시되어 있습니다.", decoration=MLogger.DECORATION_BOX)

            return True
        except MKilledException:
            return False
        except SizingException as se:
            logger.error("사이징 처리가 불가능한 데이터로 종료되었습니다.\n\n%s", se, decoration=MLogger.DECORATION_BOX)
            return False
        except Exception as e:
            logger.critical("사이징처리가 의도치 않은 오류로 종료되었습니다.", e, decoration=MLogger.DECORATION_BOX)
            return False
        finally:
            logging.shutdown()
