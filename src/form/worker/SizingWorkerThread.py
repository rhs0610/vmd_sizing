# -*- coding: utf-8 -*-
#

import os
import time
import wx
import re
import gc

from form.worker.BaseWorkerThread import BaseWorkerThread, task_takes_time
from module.MOptions import MOptions, MOptionsDataSet, MArmProcessOptions, MLegProcessOptions
from service.SizingService import SizingService
from utils import MFileUtils # noqa
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)


class SizingWorkerThread(BaseWorkerThread):

    def __init__(self, frame: wx.Frame, result_event: wx.Event, target_idx: int, is_exec_saving: bool, is_out_log: bool):
        self.elapsed_time = 0
        self.is_out_log = is_out_log
        self.is_exec_saving = is_exec_saving
        self.target_idx = target_idx
        self.gauge_ctrl = frame.file_panel_ctrl.gauge_ctrl
        self.options = None
        self.output_log_path = None

        super().__init__(frame, result_event, frame.file_panel_ctrl.console_ctrl)

    @task_takes_time
    def thread_event(self):
        try:
            start = time.time()
            # データセットリスト
            data_set_list = []
            total_process = 0
            self.frame.file_panel_ctrl.tree_process_dict = {}

            now_camera_output_vmd_path = None
            now_camera_data = None
            now_camera_path = self.frame.camera_panel_ctrl.camera_vmd_file_ctrl.file_ctrl.GetPath()
            if len(now_camera_path) > 0:
                now_camera_data = self.frame.camera_panel_ctrl.camera_vmd_file_ctrl.data.copy()
                now_camera_output_vmd_path = self.frame.camera_panel_ctrl.output_camera_vmd_file_ctrl.file_ctrl.GetPath()

            if self.frame.file_panel_ctrl.file_set.is_loaded():

                proccess_key = "【No.1】{0}({1})".format( \
                    os.path.basename(self.frame.file_panel_ctrl.file_set.motion_vmd_file_ctrl.data.path), \
                    self.frame.file_panel_ctrl.file_set.rep_model_file_ctrl.data.name)

                camera_offset_y = 0
                camera_org_model = None
                if len(now_camera_path) > 0:
                    camera_org_model = self.frame.file_panel_ctrl.file_set.org_model_file_ctrl.data
                    if 1 in self.frame.camera_panel_ctrl.camera_set_dict:
                        if self.frame.camera_panel_ctrl.camera_set_dict[1].camera_model_file_ctrl.is_set_path():
                            # 카메라元モデルが指定されている場合、카메라元モデル再指定
                            camera_org_model = self.frame.camera_panel_ctrl.camera_set_dict[1].camera_model_file_ctrl.data
                        camera_offset_y = self.frame.camera_panel_ctrl.camera_set_dict[1].camera_offset_y_ctrl.GetValue()

                morph_list, morph_seted = self.frame.morph_panel_ctrl.get_morph_list(1, self.frame.file_panel_ctrl.file_set.motion_vmd_file_ctrl.data.digest, \
                    self.frame.file_panel_ctrl.file_set.org_model_file_ctrl.data.digest, self.frame.file_panel_ctrl.file_set.rep_model_file_ctrl.data.digest)   # noqa

                if not self.frame.camera_panel_ctrl.camera_only_flg_ctrl.GetValue():
                    # 1件目のモーションとモデル
                    self.frame.file_panel_ctrl.tree_process_dict[proccess_key] = {"이동 축척 보정": False}

                    total_process += 2                                                                                      # 基本보정・腕자세보정
                    if self.frame.file_panel_ctrl.file_set.org_model_file_ctrl.title_parts_ctrl.GetValue() > 0:
                        total_process += len(self.frame.file_panel_ctrl.file_set.get_selected_stance_details())             # 자세추가보정
                        self.frame.file_panel_ctrl.tree_process_dict[proccess_key]["자세 추가 보정"] = {}

                        for v in self.frame.file_panel_ctrl.file_set.get_selected_stance_details():
                            self.frame.file_panel_ctrl.tree_process_dict[proccess_key]["자세 추가 보정"][v] = False

                    self.frame.file_panel_ctrl.tree_process_dict[proccess_key]["팔 자세 보정"] = False

                    total_process += self.frame.file_panel_ctrl.file_set.rep_model_file_ctrl.title_parts_ctrl.GetValue()    # 비틀림 분산
                    if self.frame.file_panel_ctrl.file_set.rep_model_file_ctrl.title_parts_ctrl.GetValue() == 1:
                        self.frame.file_panel_ctrl.tree_process_dict[proccess_key]["비틀림 분산"] = False

                    if self.frame.arm_panel_ctrl.arm_process_flg_avoidance.GetValue() > 0:
                        self.frame.file_panel_ctrl.tree_process_dict[proccess_key]["접촉 회피"] = False

                    if morph_seted:
                        total_process += 1  # 모프치환
                        self.frame.file_panel_ctrl.tree_process_dict[proccess_key]["모프 치환"] = False

                # 1件目は必ず読み込む
                first_data_set = MOptionsDataSet(
                    motion=self.frame.file_panel_ctrl.file_set.motion_vmd_file_ctrl.data.copy(), \
                    org_model=self.frame.file_panel_ctrl.file_set.org_model_file_ctrl.data, \
                    rep_model=self.frame.file_panel_ctrl.file_set.rep_model_file_ctrl.data, \
                    output_vmd_path=self.frame.file_panel_ctrl.file_set.output_vmd_file_ctrl.file_ctrl.GetPath(), \
                    detail_stance_flg=self.frame.file_panel_ctrl.file_set.org_model_file_ctrl.title_parts_ctrl.GetValue(), \
                    twist_flg=self.frame.file_panel_ctrl.file_set.rep_model_file_ctrl.title_parts_ctrl.GetValue(), \
                    morph_list=morph_list, \
                    camera_org_model=camera_org_model, \
                    camera_offset_y=camera_offset_y, \
                    selected_stance_details=self.frame.file_panel_ctrl.file_set.get_selected_stance_details()
                )
                data_set_list.append(first_data_set)

            # 2件目以降は有効なのだけ読み込む
            for multi_idx, file_set in enumerate(self.frame.multi_panel_ctrl.file_set_list):
                if file_set.is_loaded():

                    proccess_key = "【No.{0}】{1}({2})".format( \
                        file_set.set_no, \
                        os.path.basename(file_set.motion_vmd_file_ctrl.data.path), \
                        file_set.rep_model_file_ctrl.data.name)

                    # 2件目移行のモーションとモデル
                    morph_list, morph_seted = self.frame.morph_panel_ctrl.get_morph_list(file_set.set_no, file_set.motion_vmd_file_ctrl.data.digest, \
                        file_set.org_model_file_ctrl.data.digest, file_set.rep_model_file_ctrl.data.digest)   # noqa

                    if not self.frame.camera_panel_ctrl.camera_only_flg_ctrl.GetValue():
                        self.frame.file_panel_ctrl.tree_process_dict[proccess_key] = {"이동 축척 보정": False}

                        total_process += 2                                                                          # 基本보정・腕자세보정
                        if file_set.org_model_file_ctrl.title_parts_ctrl.GetValue() > 0:
                            total_process += len(file_set.get_selected_stance_details())                            # 자세추가보정
                            self.frame.file_panel_ctrl.tree_process_dict[proccess_key]["자세 추가 보정"] = {}

                            for v in file_set.get_selected_stance_details():
                                self.frame.file_panel_ctrl.tree_process_dict[proccess_key]["자세 추가 보정"][v] = False

                        total_process += file_set.rep_model_file_ctrl.title_parts_ctrl.GetValue()                   # 비틀림 분산
                        if file_set.rep_model_file_ctrl.title_parts_ctrl.GetValue() == 1:
                            self.frame.file_panel_ctrl.tree_process_dict[proccess_key]["비틀림 분산"] = False

                        self.frame.file_panel_ctrl.tree_process_dict[proccess_key]["팔 자세 보정"] = False

                        if self.frame.arm_panel_ctrl.arm_process_flg_avoidance.GetValue() > 0:
                            self.frame.file_panel_ctrl.tree_process_dict[proccess_key]["접촉 회피"] = False

                        if morph_seted:
                            total_process += 1  # 모프치환
                            self.frame.file_panel_ctrl.tree_process_dict[proccess_key]["모프 치환"] = False

                    camera_offset_y = 0
                    camera_org_model = file_set.org_model_file_ctrl.data
                    if multi_idx + 2 in self.frame.camera_panel_ctrl.camera_set_dict:
                        if self.frame.camera_panel_ctrl.camera_set_dict[multi_idx + 2].camera_model_file_ctrl.is_set_path():
                            # 카메라元モデルが指定されている場合、카메라元モデル再指定
                            camera_org_model = self.frame.camera_panel_ctrl.camera_set_dict[multi_idx + 2].camera_model_file_ctrl.data
                        camera_offset_y = self.frame.camera_panel_ctrl.camera_set_dict[multi_idx + 2].camera_offset_y_ctrl.GetValue()

                    multi_data_set = MOptionsDataSet(
                        motion=file_set.motion_vmd_file_ctrl.data.copy(), \
                        org_model=file_set.org_model_file_ctrl.data, \
                        rep_model=file_set.rep_model_file_ctrl.data, \
                        output_vmd_path=file_set.output_vmd_file_ctrl.file_ctrl.GetPath(), \
                        detail_stance_flg=file_set.org_model_file_ctrl.title_parts_ctrl.GetValue(), \
                        twist_flg=file_set.rep_model_file_ctrl.title_parts_ctrl.GetValue(), \
                        morph_list=morph_list, \
                        camera_org_model=camera_org_model, \
                        camera_offset_y=camera_offset_y, \
                        selected_stance_details=file_set.get_selected_stance_details()
                    )
                    data_set_list.append(multi_data_set)

            total_process += self.frame.arm_panel_ctrl.arm_process_flg_avoidance.GetValue() * len(data_set_list)    # 접촉 회피
            total_process += self.frame.arm_panel_ctrl.arm_process_flg_alignment.GetValue()                         # 位置合わせ
            if not self.frame.camera_panel_ctrl.camera_only_flg_ctrl.GetValue() and self.frame.arm_panel_ctrl.arm_process_flg_alignment.GetValue() > 0:
                self.frame.file_panel_ctrl.tree_process_dict["위치 맞추기"] = False

            if len(now_camera_path) > 0:
                total_process += 1                                                                                  # 카메라
                self.frame.file_panel_ctrl.tree_process_dict["카메라 보정"] = False

            self.options = MOptions(\
                version_name=self.frame.version_name, \
                logging_level=self.frame.logging_level, \
                data_set_list=data_set_list, \
                arm_options=MArmProcessOptions( \
                    self.frame.arm_panel_ctrl.arm_process_flg_avoidance.GetValue(), \
                    self.frame.arm_panel_ctrl.get_avoidance_target(), \
                    self.frame.arm_panel_ctrl.arm_process_flg_alignment.GetValue(), \
                    self.frame.arm_panel_ctrl.arm_alignment_finger_flg_ctrl.GetValue(), \
                    self.frame.arm_panel_ctrl.arm_alignment_floor_flg_ctrl.GetValue(), \
                    self.frame.arm_panel_ctrl.alignment_distance_wrist_slider.GetValue(), \
                    self.frame.arm_panel_ctrl.alignment_distance_finger_slider.GetValue(), \
                    self.frame.arm_panel_ctrl.alignment_distance_floor_slider.GetValue(), \
                    self.frame.arm_panel_ctrl.arm_check_skip_flg_ctrl.GetValue()
                ), \
                leg_options=MLegProcessOptions(
                    move_correction_ratio=self.frame.leg_panel_ctrl.move_correction_slider.GetValue(),
                    leg_offsets=self.frame.leg_panel_ctrl.get_leg_offsets()
                ), \
                camera_motion=now_camera_data, \
                camera_output_vmd_path=now_camera_output_vmd_path, \
                is_sizing_camera_only=self.frame.camera_panel_ctrl.camera_only_flg_ctrl.GetValue(), \
                camera_length=self.frame.camera_panel_ctrl.camera_length_slider.GetValue(), \
                monitor=self.frame.file_panel_ctrl.console_ctrl, \
                is_file=False, \
                outout_datetime=logger.outout_datetime, \
                max_workers=(1 if self.is_exec_saving else min(32, os.cpu_count() + 4)), \
                total_process=total_process, \
                now_process=0, \
                total_process_ctrl=self.frame.file_panel_ctrl.total_process_ctrl, \
                now_process_ctrl=self.frame.file_panel_ctrl.now_process_ctrl, \
                tree_process_dict=self.frame.file_panel_ctrl.tree_process_dict)

            self.result = SizingService(self.options).execute() and self.result

            self.elapsed_time = time.time() - start
        except Exception as e:
            logger.critical("VMD사이징 처리가 의도치 않은 오류로 종료되었습니다.", e, decoration=MLogger.DECORATION_BOX)
        finally:
            try:
                logger.debug("★★★result: %s, is_killed: %s", self.result, self.is_killed)
                if self.is_out_log or (not self.result and not self.is_killed):
                    # ログパス生成
                    output_vmd_path = self.frame.file_panel_ctrl.file_set.output_vmd_file_ctrl.file_ctrl.GetPath()
                    self.output_log_path = re.sub(r'\.vmd$', '.log', output_vmd_path)

                    # 出力されたメッセージを全部出力
                    self.frame.file_panel_ctrl.console_ctrl.SaveFile(filename=self.output_log_path)

            except Exception:
                pass

    def thread_delete(self):
        del self.options
        gc.collect()

    def post_event(self):
        wx.PostEvent(self.frame, self.result_event(result=self.result and not self.is_killed, target_idx=self.target_idx, elapsed_time=self.elapsed_time, output_log_path=self.output_log_path))

