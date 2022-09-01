# -*- coding: utf-8 -*-
#
import wx
import wx.lib.newevent
import sys
import csv
import re
import os
from datetime import datetime

from form.panel.BasePanel import BasePanel
from form.parts.HistoryFilePickerCtrl import HistoryFilePickerCtrl
from form.parts.ConsoleCtrl import ConsoleCtrl
from form.parts.SizingFileSet import SizingFileSet
from form.worker.SizingWorkerThread import SizingWorkerThread
from form.worker.LoadWorkerThread import LoadWorkerThread
from utils import MFormUtils, MFileUtils # noqa
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)
TIMER_ID = wx.NewId()

# イベント
(BulkSizingThreadEvent, EVT_BULK_SIZING_THREAD) = wx.lib.newevent.NewEvent()
(BulkLoadThreadEvent, EVT_BULK_LOAD_THREAD) = wx.lib.newevent.NewEvent()


class BulkPanel(BasePanel):

    def __init__(self, frame: wx.Frame, parent: wx.Notebook, tab_idx: int):
        super().__init__(frame, parent, tab_idx)

        self.description_txt = wx.StaticText(self, wx.ID_ANY, "설정을 일괄로 지정하여 연속적으로 처리시킬 수 있습니다.", wx.DefaultPosition, wx.DefaultSize, 0)
        self.sizer.Add(self.description_txt, 0, wx.ALL, 5)

        self.static_line = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.sizer.Add(self.static_line, 0, wx.EXPAND | wx.ALL, 5)

        # バルクBULKファイルコントロール
        self.bulk_csv_file_ctrl = HistoryFilePickerCtrl(frame, self, u"일괄 처리용 CSV", u"일괄 처리용 CSV 파일 열기", ("csv"), wx.FLP_DEFAULT_STYLE, \
                                                        u"일괄 처리용 CSV를 지정하십시오.\n포맷은 DL버튼을 통해 얻을 수 있습니다.\nD&D에서의 지정, 열기 버튼에서의 지정, 이력에서의 선택을 할 수 있습니다.", \
                                                        file_model_spacer=0, title_parts_ctrl=None, title_parts2_ctrl=None, \
                                                        file_histories_key="bulk_csv", is_change_output=False, is_aster=False, is_save=False, set_no=0)
        self.sizer.Add(self.bulk_csv_file_ctrl.sizer, 0, wx.EXPAND | wx.ALL, 0)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 一括サイジング保存ボタン
        self.save_btn_ctrl = wx.Button(self, wx.ID_ANY, u"일괄 사이징 저장", wx.DefaultPosition, wx.Size(150, 50), 0)
        self.save_btn_ctrl.SetToolTip(u"현재의 사이징 설정을 CSV에 저장합니다.")
        self.save_btn_ctrl.Bind(wx.EVT_LEFT_DCLICK, self.on_doubleclick)
        self.save_btn_ctrl.Bind(wx.EVT_LEFT_DOWN, self.on_save_click)
        btn_sizer.Add(self.save_btn_ctrl, 0, wx.ALL, 5)

        # 一括サイジング確認ボタン
        self.check_btn_ctrl = wx.Button(self, wx.ID_ANY, u"일괄 사이징 확인", wx.DefaultPosition, wx.Size(150, 50), 0)
        self.check_btn_ctrl.SetToolTip(u"지정된 CSV 데이터의 설정을 확인합니다.")
        self.check_btn_ctrl.Bind(wx.EVT_LEFT_DCLICK, self.on_doubleclick)
        self.check_btn_ctrl.Bind(wx.EVT_LEFT_DOWN, self.on_check_click)
        btn_sizer.Add(self.check_btn_ctrl, 0, wx.ALL, 5)

        # 一括サイジング実行ボタン
        self.bulk_btn_ctrl = wx.Button(self, wx.ID_ANY, u"일괄 사이징 실행", wx.DefaultPosition, wx.Size(150, 50), 0)
        self.bulk_btn_ctrl.SetToolTip(u"일괄적으로 사이징을 실행합니다")
        self.bulk_btn_ctrl.Bind(wx.EVT_LEFT_DCLICK, self.on_doubleclick)
        self.bulk_btn_ctrl.Bind(wx.EVT_LEFT_DOWN, self.on_bulk_click)
        btn_sizer.Add(self.bulk_btn_ctrl, 0, wx.ALL, 5)

        self.sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.SHAPED, 5)

        # コンソール
        self.console_ctrl = ConsoleCtrl(self, self.frame.logging_level, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.Size(-1, 420), \
                                        wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_NONE | wx.HSCROLL | wx.VSCROLL | wx.WANTS_CHARS)
        self.console_ctrl.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DLIGHT))
        self.console_ctrl.Bind(wx.EVT_CHAR, lambda event: MFormUtils.on_select_all(event, self.console_ctrl))
        self.sizer.Add(self.console_ctrl, 1, wx.ALL | wx.EXPAND, 5)

        # ゲージ
        self.gauge_ctrl = wx.Gauge(self, wx.ID_ANY, 100, wx.DefaultPosition, wx.DefaultSize, wx.GA_HORIZONTAL)
        self.gauge_ctrl.SetValue(0)
        self.sizer.Add(self.gauge_ctrl, 0, wx.ALL | wx.EXPAND, 5)

        self.fit()

        # 変換完了処理バインド
        self.frame.Bind(EVT_BULK_LOAD_THREAD, self.on_load_result)
        self.frame.Bind(EVT_BULK_SIZING_THREAD, self.on_exec_result)

    # フォーム無効化
    def disable(self):
        self.bulk_csv_file_ctrl.disable()
        self.bulk_btn_ctrl.Disable()
        self.check_btn_ctrl.Disable()

    # フォーム無効化
    def enable(self):
        self.bulk_csv_file_ctrl.enable()
        self.bulk_btn_ctrl.Enable()
        self.check_btn_ctrl.Enable()

    def on_doubleclick(self, event: wx.Event):
        self.timer.Stop()
        logger.warning("더블클릭 되었습니다.", decoration=MLogger.DECORATION_BOX)
        event.Skip(False)
        return False

    def on_bulk_click(self, event: wx.Event):
        self.timer = wx.Timer(self, TIMER_ID)
        self.timer.Start(200)
        self.Bind(wx.EVT_TIMER, self.on_bulk, id=TIMER_ID)

    # サイジング一括実行
    def on_bulk(self, event: wx.Event):
        if self.timer:
            self.timer.Stop()
            self.Unbind(wx.EVT_TIMER, id=TIMER_ID)

        # 出力先をファイルパネルのコンソールに変更
        sys.stdout = self.console_ctrl

        if self.bulk_btn_ctrl.GetLabel() == "일괄 사이징 정지" and self.frame.worker:
            # フォーム無効化
            self.disable()
            # 停止状態でボタン押下時、停止
            self.frame.worker.stop()

            # タブ移動可
            self.release_tab()
            # フォーム有効化
            self.enable()
            # ワーカー終了
            self.frame.worker = None
            # プログレス非表示
            self.gauge_ctrl.SetValue(0)

            logger.warning("VMD 사이징 일괄 처리를 중단합니다.", decoration=MLogger.DECORATION_BOX)

            event.Skip(False)
        elif not self.frame.worker:
            # フォーム無効化
            self.disable()
            # タブ固定
            self.fix_tab()
            # コンソールクリア
            self.console_ctrl.Clear()

            # 履歴保持
            self.save()

            # サイジング可否체크の後に実行
            self.check(event, True)

            event.Skip()
        else:
            logger.error("아직 처리가 진행 중입니다.종료 후 다시 실행해 주세요.", decoration=MLogger.DECORATION_BOX)
            event.Skip(False)

    def on_save_click(self, event: wx.Event):
        self.timer = wx.Timer(self, TIMER_ID)
        self.timer.Start(200)
        self.Bind(wx.EVT_TIMER, self.on_save, id=TIMER_ID)

    # サイジング一括データ保存
    def on_save(self, event: wx.Event):
        if self.timer:
            self.timer.Stop()
            self.Unbind(wx.EVT_TIMER, id=TIMER_ID)

        # 一括タブのコンソール
        sys.stdout = self.console_ctrl

        if not self.frame.file_panel_ctrl.file_set.motion_vmd_file_ctrl.path():
            logger.warning("파일 탭의 '조정 대상 모션 VMD/VPD'가 공란으로 인해 처리를 중단합니다.", decoration=MLogger.DECORATION_BOX)
            return

        save_key = ["그룹No(복수인 모션은 동일No)", "조정대상 모션 VMD/VPD(풀패스)", "모션 작성 원본 모델 PMX(풀패스)", "모션 변환용 모델 PMX(풀패스)", \
                    "센터XZ 보정(0:무효, 1:유효)", "상체 보정(0:무효, 1:유효)", "하체 보정(0:무효, 1:유효)", "다리 IK 보정(0:무효, 1:유효)", "발끝 보정(0:무효, 1:유효)", \
                    "발끝 IK 보정(0:무효, 1:유효)", "어깨 보정(0:무효, 1:유효)", "센터 Y 보정(0:무효, 1:유효)", "비틀림 분산(0:없음, 1:있음)", "모프 치환(원:끝:크기;)", "접촉 회피(0:없음, 1:유효)", \
                    "접촉회피 강체(강체명;)", "위치맞춤(0:없음, 1:있음)", "손가락위치맞춤(0:없음, 1:있음)", "바닥위치맞춤(0:없음, 1:있음)", "손목거리", "손가락거리", "바닥과의거리", \
                    "팔 체크 스킵(0:없음, 1:있음)", "전체 이동량 보정치", "다리 IK 오프셋", "카메라 모션 VMD(풀패스, 그룹 1건만)", "거리가동범위", "카메라 작성 원본 모델 PMX(풀패스)", "전체 길이 Y 오프셋"]

        output_path = os.path.join(os.path.dirname(self.frame.file_panel_ctrl.file_set.motion_vmd_file_ctrl.path()), f'일괄 사이징용 데이터_{datetime.now():%Y%m%d_%H%M%S}.csv')

        with open(output_path, 'w', encoding='cp932', newline='') as f:
            writer = csv.DictWriter(f, save_key)
            writer.writeheader()
            writer.writerow(self.create_save_data(self.frame.file_panel_ctrl.file_set, 0, save_key))

            for multi_idx, file_set in enumerate(self.frame.multi_panel_ctrl.file_set_list):
                writer.writerow(self.create_save_data(file_set, multi_idx + 1, save_key))

        self.frame.sound_finish()
        event.Skip()

        logger.info("일괄 사이징용 데이터 저장에 성공했습니다\n\n%s", output_path, decoration=MLogger.DECORATION_BOX)
        return

    def create_save_data(self, file_set: SizingFileSet, file_idx: int, save_key: list):

        save_data = {}
        for skey in save_key:
            save_data[skey] = ""

        save_data[save_key[0]] = "1"
        save_data[save_key[1]] = file_set.motion_vmd_file_ctrl.path()
        save_data[save_key[2]] = file_set.org_model_file_ctrl.path()
        save_data[save_key[3]] = file_set.rep_model_file_ctrl.path()
        save_data[save_key[4]] = "1" if 0 in file_set.selected_stance_details and file_set.org_model_file_ctrl.title_parts_ctrl.GetValue() else "0"
        save_data[save_key[5]] = "1" if 1 in file_set.selected_stance_details and file_set.org_model_file_ctrl.title_parts_ctrl.GetValue() else "0"
        save_data[save_key[6]] = "1" if 2 in file_set.selected_stance_details and file_set.org_model_file_ctrl.title_parts_ctrl.GetValue() else "0"
        save_data[save_key[7]] = "1" if 3 in file_set.selected_stance_details and file_set.org_model_file_ctrl.title_parts_ctrl.GetValue() else "0"
        save_data[save_key[8]] = "1" if 4 in file_set.selected_stance_details and file_set.org_model_file_ctrl.title_parts_ctrl.GetValue() else "0"
        save_data[save_key[9]] = "1" if 5 in file_set.selected_stance_details and file_set.org_model_file_ctrl.title_parts_ctrl.GetValue() else "0"
        save_data[save_key[10]] = "1" if 6 in file_set.selected_stance_details and file_set.org_model_file_ctrl.title_parts_ctrl.GetValue() else "0"
        save_data[save_key[11]] = "1" if 7 in file_set.selected_stance_details and file_set.org_model_file_ctrl.title_parts_ctrl.GetValue() else "0"
        save_data[save_key[12]] = "1" if file_set.rep_model_file_ctrl.title_parts_ctrl.GetValue() else "0"
        save_data[save_key[13]] = ";".join([f"{om}:{rm}:{r}" for (om, rm, r) in self.frame.morph_panel_ctrl.morph_set_dict[file_idx].get_morph_list()]) + ";" \
            if file_idx in self.frame.morph_panel_ctrl.morph_set_dict else ""
        save_data[save_key[14]] = "1" if self.frame.arm_panel_ctrl.arm_process_flg_avoidance.GetValue() else "0"
        save_data[save_key[15]] = ";".join(list(self.frame.arm_panel_ctrl.get_avoidance_target()[file_idx])) + ";" if file_idx in self.frame.arm_panel_ctrl.get_avoidance_target() else ""
        save_data[save_key[16]] = "1" if self.frame.arm_panel_ctrl.arm_process_flg_alignment.GetValue() else "0"
        save_data[save_key[17]] = "1" if self.frame.arm_panel_ctrl.arm_alignment_finger_flg_ctrl.GetValue() else "0"
        save_data[save_key[18]] = "1" if self.frame.arm_panel_ctrl.arm_alignment_floor_flg_ctrl.GetValue() else "0"
        save_data[save_key[19]] = self.frame.arm_panel_ctrl.alignment_distance_wrist_slider.GetValue()
        save_data[save_key[20]] = self.frame.arm_panel_ctrl.alignment_distance_finger_slider.GetValue()
        save_data[save_key[21]] = self.frame.arm_panel_ctrl.alignment_distance_floor_slider.GetValue()
        save_data[save_key[22]] = "1" if self.frame.arm_panel_ctrl.arm_check_skip_flg_ctrl.GetValue() else "0"
        save_data[save_key[23]] = self.frame.leg_panel_ctrl.move_correction_slider.GetValue()
        save_data[save_key[24]] = self.frame.leg_panel_ctrl.get_leg_offsets()[file_idx] if file_idx in self.frame.leg_panel_ctrl.get_leg_offsets() else "0"
        save_data[save_key[25]] = self.frame.camera_panel_ctrl.camera_vmd_file_ctrl.file_ctrl.GetPath()
        save_data[save_key[26]] = self.frame.camera_panel_ctrl.camera_length_slider.GetValue()
        save_data[save_key[27]] = self.frame.camera_panel_ctrl.camera_set_dict[file_idx + 1].camera_model_file_ctrl.path() if file_idx + 1 in self.frame.camera_panel_ctrl.camera_set_dict else ""
        save_data[save_key[28]] = self.frame.camera_panel_ctrl.camera_set_dict[file_idx + 1].camera_offset_y_ctrl.GetValue() if file_idx + 1 in self.frame.camera_panel_ctrl.camera_set_dict else ""

        return save_data

    def on_check_click(self, event: wx.Event):
        self.timer = wx.Timer(self, TIMER_ID)
        self.timer.Start(200)
        self.Bind(wx.EVT_TIMER, self.on_check, id=TIMER_ID)

    # サイジング一括確認
    def on_check(self, event: wx.Event):
        if self.timer:
            self.timer.Stop()
            self.Unbind(wx.EVT_TIMER, id=TIMER_ID)

        # 出力先をファイルパネルのコンソールに変更
        sys.stdout = self.console_ctrl

        # サイジング可否체크のみ
        self.check(event, False)
        return

    def save(self):
        # 履歴保持
        self.bulk_csv_file_ctrl.save()

        # JSON出力
        MFileUtils.save_history(self.frame.mydir_path, self.frame.file_hitories)

    # データ체크
    def check(self, event: wx.Event, is_exec: bool):
        # フォーム無効化
        self.disable()
        # タブ固定
        self.fix_tab()

        if not self.bulk_csv_file_ctrl.is_valid():
            # CSVパスが無効な場合、終了
            self.enable()
            self.release_tab()
            return

        result = True
        with open(self.bulk_csv_file_ctrl.path(), encoding='cp932', mode='r') as f:
            reader = csv.reader(f)
            next(reader)  # ヘッダーを読み飛ばす

            prev_group_no = -1
            now_model_no = -1
            service_data_txt = ""
            for ridx, rows in enumerate(reader):
                row_no = ridx
                group_no_result, group_no = self.read_csv_row(rows, row_no, 0, "그룹No", True, int, r"\d+", "수치만", None)
                org_motion_result, org_motion_path = self.read_csv_row(rows, row_no, 1, "조정대상 모션 VMD/VPD", True, str, None, None, (".vmd", ".vpd"))
                org_model_result, org_model_path = self.read_csv_row(rows, row_no, 2, "모션 작성 원본 모델 PMX", True, str, None, None, (".pmx"))
                rep_model_result, rep_model_path = self.read_csv_row(rows, row_no, 3, "모션 변환용 모델 PMX", True, str, None, None, (".pmx"))
                stance_center_xz_result, stance_center_xz_datas = self.read_csv_row(rows, row_no, 4, "센터XZ 보정", True, int, r"^(0|1)$", "0 혹은 1", None)
                stance_upper_result, stance_upper_datas = self.read_csv_row(rows, row_no, 5, "상체 보정", True, int, r"^(0|1)$", "0 혹은 1", None)
                stance_lower_result, stance_lower_datas = self.read_csv_row(rows, row_no, 6, "하체 보정", True, int, r"^(0|1)$", "0 혹은 1", None)
                stance_leg_ik_result, stance_leg_ik_datas = self.read_csv_row(rows, row_no, 7, "다리 IK 보정", True, int, r"^(0|1)$", "0 혹은 1", None)
                stance_toe_result, stance_toe_datas = self.read_csv_row(rows, row_no, 8, "발끝보정", True, int, r"^(0|1)$", "0 혹은 1", None)
                stance_toe_ik_result, stance_toe_ik_datas = self.read_csv_row(rows, row_no, 9, "발끝 IK 보정", True, int, r"^(0|1)$", "0 혹은 1", None)
                stance_shoulder_result, stance_shoulder_datas = self.read_csv_row(rows, row_no, 10, "어깨 보정", True, int, r"^(0|1)$", "0 혹은 1", None)
                stance_center_y_result, stance_center_y_datas = self.read_csv_row(rows, row_no, 11, "센터 Y 보정", True, int, r"^(0|1)$", "0 혹은 1", None)
                separate_twist_result, separate_twist_datas = self.read_csv_row(rows, row_no, 12, "비틀어 분산", True, int, r"^(0|1)$", "0 혹은 1", None)
                morph_result, morph_datas = self.read_csv_row(rows, row_no, 13, "모프치환", False, str, r"[^\:]+\:[^\:]+\:\d+\.?\d*\;", "원본:변환용:크기;", None)
                arm_avoidance_result, arm_avoidance_datas = self.read_csv_row(rows, row_no, 14, "접촉회피", True, int, r"^(0|1)$", "0 혹은 1", None)
                avoidance_name_result, avoidance_name_datas = self.read_csv_row(rows, row_no, 15, "접촉회피강체", False, str, r"[^\;]+\;", "강체명;", None)
                arm_alignment_result, arm_alignment_datas = self.read_csv_row(rows, row_no, 16, "위치맞춤", True, int, r"^(0|1)$", "0 혹은 1", None)
                finger_alignment_result, finger_alignment_datas = self.read_csv_row(rows, row_no, 17, "손가락위치맞춤", False, int, r"^(0|1)$", "0 혹은 1", None)
                floor_alignment_result, floor_alignment_datas = self.read_csv_row(rows, row_no, 18, "바닥위치맞춤", False, int, r"^(0|1)$", "0 혹은 1", None)
                arm_alignment_length_result, arm_alignment_length_datas = self.read_csv_row(rows, row_no, 19, "손목거리", False, float, None, None, None)
                finger_alignment_length_result, finger_alignment_length_datas = self.read_csv_row(rows, row_no, 20, "손가락거리", False, float, None, None, None)
                floor_alignment_length_result, floor_alignment_length_datas = self.read_csv_row(rows, row_no, 21, "바닥과의 거리", False, float, None, None, None)
                arm_check_skip_result, arm_check_skip_datas = self.read_csv_row(rows, row_no, 22, "팔체크스킵", True, int, r"^(0|1)$", "0 혹은 1", None)
                move_correction_result, move_correction_data = self.read_csv_row(rows, row_no, 23, "전체 이동량 보정", False, float, None, None, None)
                leg_offset_result, leg_offset_data = self.read_csv_row(rows, row_no, 24, "다리 IK 오프셋 값", False, float, None, None, None)
                org_camera_motion_result, org_camera_motion_path = self.read_csv_row(rows, row_no, 25, "카메라 모션 VMD", False, str, None, None, (".vmd"))
                camera_length_result, camera_length_datas = self.read_csv_row(rows, row_no, 26, "거리가동범위", False, float, r"^[1-9]\d*\.?\d*", "1이상", None)
                org_camera_model_result, org_camera_model_path = self.read_csv_row(rows, row_no, 27, "카메라 작성 원본 모델 PMX", False, str, None, None, (".pmx"))
                camera_y_offset_result, camera_y_offset_datas = self.read_csv_row(rows, row_no, 28, "전체 길이 Y 오프셋", False, float, None, None, None)

                result = result & group_no_result & org_motion_result & org_model_result & rep_model_result & stance_center_xz_result \
                    & stance_upper_result & stance_lower_result & stance_leg_ik_result & stance_toe_result & stance_toe_ik_result & stance_shoulder_result \
                    & stance_center_y_result & separate_twist_result & arm_check_skip_result & morph_result & arm_avoidance_result & avoidance_name_result \
                    & arm_alignment_result & finger_alignment_result & floor_alignment_result & arm_alignment_length_result & finger_alignment_length_result \
                    & floor_alignment_length_result & org_camera_motion_result & camera_length_result & org_camera_model_result \
                    & camera_y_offset_result & move_correction_result & leg_offset_result

                if result:
                    if prev_group_no != group_no[0]:
                        now_model_no = 1

                        if len(service_data_txt) > 0:
                            # 既存データがある場合、出力
                            logger.info(service_data_txt, decoration=MLogger.DECORATION_BOX)

                        # 先頭모션の場合
                        service_data_txt = f"\n【그룹No.{group_no[0]}】 \n"

                        arm_avoidance_txt = "있음" if arm_avoidance_datas[0] == 1 else "없음"
                        service_data_txt = f"{service_data_txt}　강체 접촉 회피: {arm_avoidance_txt}\n"
                        arm_alignment_txt = "있음" if arm_alignment_datas[0] == 1 else "없음"
                        service_data_txt = f"{service_data_txt}　손목 위치 맞춤: {arm_alignment_txt} ({arm_alignment_length_datas})\n"
                        finger_alignment_txt = "있음" if finger_alignment_datas[0] == 1 else "없음"
                        service_data_txt = f"{service_data_txt}　손가락 위치 맞춤: {finger_alignment_txt} ({finger_alignment_length_datas})\n"
                        floor_alignment_txt = "있음" if floor_alignment_datas[0] == 1 else "없음"
                        service_data_txt = f"{service_data_txt}　바닥 위치 맞춤: {floor_alignment_txt} ({floor_alignment_length_datas})\n"
                        arm_check_skip_txt = "있음" if arm_check_skip_datas[0] == 1 else "없음"
                        service_data_txt = f"{service_data_txt}　팔 체크 스킵: {arm_check_skip_txt}\n"
                        service_data_txt = f"{service_data_txt}　전체 이동량 보정치: {move_correction_data}\n"

                        service_data_txt = f"{service_data_txt}　카메라: {org_camera_motion_path}\n"
                        service_data_txt = f"{service_data_txt}　거리 제한: {camera_length_datas}\n"
                    else:
                        # 複数人모션の場合、No加算
                        now_model_no += 1

                    service_data_txt = f"{service_data_txt}\n　【인물No.{now_model_no}】 --------- \n"

                    service_data_txt = f"{service_data_txt}　　모션: {org_motion_path}\n"
                    service_data_txt = f"{service_data_txt}　　작성 원본 모델: {org_model_path}\n"
                    service_data_txt = f"{service_data_txt}　　변환용 모델ル: {rep_model_path}\n"
                    service_data_txt = f"{service_data_txt}　　발 IK 보정치: {leg_offset_data}\n"
                    service_data_txt = f"{service_data_txt}　　카메라 작성 원본 모델: {org_camera_model_path}\n"
                    service_data_txt = f"{service_data_txt}　　Y 오프셋: {camera_y_offset_datas}\n"

                    detail_stance_list = []
                    if stance_center_xz_datas[0] == 1:
                        detail_stance_list.append("센터 XZ 보정")
                    if stance_upper_datas[0] == 1:
                        detail_stance_list.append("상반신 보정")
                    if stance_lower_datas[0] == 1:
                        detail_stance_list.append("하반신 보정")
                    if stance_leg_ik_datas[0] == 1:
                        detail_stance_list.append("발 IK 보정")
                    if stance_toe_datas[0] == 1:
                        detail_stance_list.append("발끝 보정")
                    if stance_toe_ik_datas[0] == 1:
                        detail_stance_list.append("발끝 IK 보정")
                    if stance_shoulder_datas[0] == 1:
                        detail_stance_list.append("어깨 보정")
                    if stance_center_y_datas[0] == 1:
                        detail_stance_list.append("센터 Y 보정")
                    detail_stance_txt = ", ".join(detail_stance_list)

                    service_data_txt = f"{service_data_txt}　　자세 추가 보정 유무: {detail_stance_txt}\n"

                    twist_txt = "있음" if separate_twist_datas[0] == 1 else "없음"
                    service_data_txt = f"{service_data_txt}　　비틀림 분산 유무: {twist_txt}\n"

                    # 모프データ
                    morph_list = []
                    for morph_data in morph_datas:
                        m = re.findall(r"([^\:]+)\:([^\:]+)\:(\d+\.?\d*)\;", morph_data)
                        morph_list.append(f"{m[0][0]} → {m[0][1]} ({float(m[0][2])})")
                    morph_txt = ", ".join(morph_list)
                    service_data_txt = f"{service_data_txt}　　모프 치환: {morph_txt}\n"

                    # 接触回避データ
                    arm_avoidance_name_list = []
                    for avoidance_data in avoidance_name_datas:
                        m = re.findall(r"([^\:]+)\;", avoidance_data)
                        arm_avoidance_name_list.append(m[0])
                    arm_avoidance_name_txt = ", ".join(arm_avoidance_name_list)
                    service_data_txt = f"{service_data_txt}　　대상 강체명: {arm_avoidance_name_txt}\n"

                prev_group_no = group_no[0]

        if result:
            if is_exec:
                # 全部OKなら処理開始
                self.load(event, 0)
            else:

                if len(service_data_txt) > 0:
                    # 既存データがある場合、最後に出力
                    logger.info(service_data_txt, decoration=MLogger.DECORATION_BOX)

                # OKかつ確認のみの場合、出力して終了
                logger.info("CSV데이터 확인에 성공했습니다.", decoration=MLogger.DECORATION_BOX, title="OK")

                self.enable()
                self.release_tab()
                return
        else:
            logger.error("CSV데이터에 부정합이 있어 처리를 중단합니다.", decoration=MLogger.DECORATION_BOX)

            self.enable()
            self.release_tab()

            return

    def read_csv_row(self, rows: list, row_no: int, row_idx: int, row_name: str, row_required: bool, row_type: type, row_regex: str, row_regex_str: str, path_exts: tuple):
        try:
            if row_required and (len(rows) < row_idx or not rows[row_idx]):
                logger.warning("%s행째의 %s(%s열째)가 설정되어 있지 않습니다.", row_no + 1, row_name, row_idx + 1)
                return False, None

            try:
                if rows[row_idx] and not row_type(rows[row_idx]):
                    pass
            except Exception:
                row_type_str = "반각 정수" if row_type == int else "반각 숫자"
                logger.warning("%s행째의 %s(%s열째)의 형(%s)이 맞지 않습니다.", row_no + 1, row_name, row_idx + 1, row_type_str)
                return False, None

            if rows[row_idx] and row_regex and not re.findall(row_regex, rows[row_idx]):
                logger.warning("%s행째의 %s(%s열째)의 표시 형식(%s)이 맞지 않습니다.", row_no + 1, row_name, row_idx + 1, row_regex_str)
                return False, None

            if rows[row_idx] and path_exts:
                if not rows[row_idx] or (not os.path.exists(rows[row_idx]) or not os.path.isfile(rows[row_idx])):
                    logger.warning("%s행째의 %s(%s열째)의 파일이 존재하지 않습니다.", row_no + 1, row_name, row_idx + 1)
                    return False, None

                # ファイル名・拡張子
                file_name, ext = os.path.splitext(os.path.basename(rows[row_idx]))
                if (ext not in path_exts):
                    logger.warning("%s행째의 %s(%s열째)의 파일 확장자(%s)가 맞지 않습니다.", row_no + 1, row_name, row_idx + 1, \
                                   ','.join(map(str, path_exts)) if len(path_exts) > 1 else path_exts)
                    return False, None

            # 読み取り実施
            if rows[row_idx] and row_regex:
                # 正規表現の場合は、リスト変換して返す
                if row_type:
                    # 型指定がある場合は変換して返す
                    return True, [row_type(v) for v in re.findall(row_regex, rows[row_idx])]
                else:
                    return True, re.findall(row_regex, rows[row_idx])

            if (row_type == float or row_type == int) and not rows[row_idx]:
                # 数値で任意はゼロ設定
                return True, 0
            elif row_type:
                return True, row_type(rows[row_idx])

            return True, rows[row_idx]
        except Exception as e:
            logger.warning("%s행째의 %s(%s열째) 판독에 실패했습니다.\n%s", row_no + 1, row_name, row_idx + 1, e)
            return False, None

    # 読み込み
    def load(self, event, line_idx):
        # 그룹単位で設定
        now_group_no = -1
        now_motion_idx = -1
        row_no = 0
        is_buld = False
        with open(self.bulk_csv_file_ctrl.path(), encoding='cp932', mode='r') as f:
            reader = csv.reader(f)
            next(reader)  # ヘッダーを読み飛ばす

            for ridx, rows in enumerate(reader):
                row_no = ridx

                if row_no < line_idx:
                    # 自分より前の行の場合、스킵
                    continue

                group_no_result, group_no = self.read_csv_row(rows, row_no, 0, "그룹No", True, int, r"\d+", "수치만", None)

                if len(group_no) == 0:
                    # 그룹NOが取れなかったから終了
                    return

                if len(group_no) > 0 and row_no == line_idx:
                    # 指定INDEXに到達したら設定して読み取り開始
                    now_motion_idx = 0
                    now_group_no = group_no[0]
                else:
                    now_motion_idx += 1

                if len(group_no) > 0 and group_no[0] != now_group_no:
                    # 그룹NOが変わっていたら、そのまま終了
                    continue

                # bulk対象
                is_buld = True

                group_no_result, group_no = self.read_csv_row(rows, row_no, 0, "그룹No", True, int, r"\d+", "수치만", None)
                org_motion_result, org_motion_path = self.read_csv_row(rows, row_no, 1, "조정 대상 모션 VMD/VPD", True, str, None, None, (".vmd", ".vpd"))
                org_model_result, org_model_path = self.read_csv_row(rows, row_no, 2, "모션 작성 원본 모델PMX", True, str, None, None, (".pmx"))
                rep_model_result, rep_model_path = self.read_csv_row(rows, row_no, 3, "모션 변환용 모델 PMX", True, str, None, None, (".pmx"))
                stance_center_xz_result, stance_center_xz_datas = self.read_csv_row(rows, row_no, 4, "센터 XZ 보정", True, int, r"^(0|1)$", "0 혹은 1", None)
                stance_upper_result, stance_upper_datas = self.read_csv_row(rows, row_no, 5, "상반신보정", True, int, r"^(0|1)$", "0 혹은 1", None)
                stance_lower_result, stance_lower_datas = self.read_csv_row(rows, row_no, 6, "하반신보정", True, int, r"^(0|1)$", "0 혹은 1", None)
                stance_leg_ik_result, stance_leg_ik_datas = self.read_csv_row(rows, row_no, 7, "발 IK 보정", True, int, r"^(0|1)$", "0 혹은 1", None)
                stance_toe_result, stance_toe_datas = self.read_csv_row(rows, row_no, 8, "발끝 보정", True, int, r"^(0|1)$", "0 혹은 1", None)
                stance_toe_ik_result, stance_toe_ik_datas = self.read_csv_row(rows, row_no, 9, "발끝 IK 보정", True, int, r"^(0|1)$", "0 혹은 1", None)
                stance_shoulder_result, stance_shoulder_datas = self.read_csv_row(rows, row_no, 10, "어깨 보정", True, int, r"^(0|1)$", "0 혹은 1", None)
                stance_center_y_result, stance_center_y_datas = self.read_csv_row(rows, row_no, 11, "센터 Y 보정", True, int, r"^(0|1)$", "0 혹은 1", None)
                separate_twist_result, separate_twist_datas = self.read_csv_row(rows, row_no, 12, "비틀림 분산", True, int, r"^(0|1)$", "0 혹은 1", None)
                morph_result, morph_datas = self.read_csv_row(rows, row_no, 13, "모프치환", False, str, r"[^\:]+\:[^\:]+\:\d+\.?\d*\;", "원본:변환용:크기;", None)
                arm_avoidance_result, arm_avoidance_datas = self.read_csv_row(rows, row_no, 14, "접촉 회피", True, int, r"^(0|1)$", "0 혹은 1", None)
                avoidance_name_result, avoidance_name_datas = self.read_csv_row(rows, row_no, 15, "접촉 회피 강체", False, str, r"[^\;]+\;", "강체명;", None)
                arm_alignment_result, arm_alignment_datas = self.read_csv_row(rows, row_no, 16, "위치 맞춤", True, int, r"^(0|1)$", "0 혹은 1", None)
                finger_alignment_result, finger_alignment_datas = self.read_csv_row(rows, row_no, 17, "손가락 위치 맞춤", False, int, r"^(0|1)$", "0 혹은 1", None)
                floor_alignment_result, floor_alignment_datas = self.read_csv_row(rows, row_no, 18, "바닥 위치 맞춤", False, int, r"^(0|1)$", "0 혹은 1", None)
                arm_alignment_length_result, arm_alignment_length_datas = self.read_csv_row(rows, row_no, 19, "손목 거리", False, float, None, None, None)
                finger_alignment_length_result, finger_alignment_length_datas = self.read_csv_row(rows, row_no, 20, "손가락 거리", False, float, None, None, None)
                floor_alignment_length_result, floor_alignment_length_datas = self.read_csv_row(rows, row_no, 21, "바닥 거리", False, float, None, None, None)
                arm_check_skip_result, arm_check_skip_datas = self.read_csv_row(rows, row_no, 22, "팔 체크 스킵", True, int, r"^(0|1)$", "0 혹은 1", None)
                move_correction_result, move_correction_data = self.read_csv_row(rows, row_no, 23, "전체 이동량 보정", False, float, None, None, None)
                leg_offset_result, leg_offset_data = self.read_csv_row(rows, row_no, 24, "발 IK 오프셋 값", False, float, None, None, None)
                org_camera_motion_result, org_camera_motion_path = self.read_csv_row(rows, row_no, 25, "카메라 모션 VMD", False, str, None, None, (".vmd"))
                camera_length_result, camera_length_datas = self.read_csv_row(rows, row_no, 26, "거리 가동 범위", False, float, None, None, None)
                org_camera_model_result, org_camera_model_path = self.read_csv_row(rows, row_no, 27, "카메라 작성 원본 모델PMX", False, str, None, None, (".pmx"))
                camera_y_offset_result, camera_y_offset_datas = self.read_csv_row(rows, row_no, 28, "길이 Y 오프셋", False, float, None, None, None)

                if now_motion_idx == 0:
                    # 複数パネルはクリア
                    self.frame.multi_panel_ctrl.on_clear_set(event)

                    # ファイルパネル設定
                    self.frame.file_panel_ctrl.file_set.motion_vmd_file_ctrl.file_ctrl.SetPath(org_motion_path)
                    self.frame.file_panel_ctrl.file_set.org_model_file_ctrl.file_ctrl.SetPath(org_model_path)
                    self.frame.file_panel_ctrl.file_set.rep_model_file_ctrl.file_ctrl.SetPath(rep_model_path)
                    self.frame.file_panel_ctrl.file_set.output_vmd_file_ctrl.file_ctrl.SetPath("")

                    self.frame.file_panel_ctrl.file_set.org_model_file_ctrl.title_parts_ctrl.SetValue(
                        stance_center_xz_datas[0] | stance_upper_datas[0] | stance_lower_datas[0] | stance_leg_ik_datas[0] | \
                        stance_toe_datas[0] | stance_toe_ik_datas[0] | stance_shoulder_datas[0] | stance_center_y_datas[0]
                    )

                    # スタンス追加보정
                    self.frame.file_panel_ctrl.file_set.selected_stance_details = []
                    if stance_center_xz_datas[0] == 1:
                        self.frame.file_panel_ctrl.file_set.selected_stance_details.append(0)
                    if stance_upper_datas[0] == 1:
                        self.frame.file_panel_ctrl.file_set.selected_stance_details.append(1)
                    if stance_lower_datas[0] == 1:
                        self.frame.file_panel_ctrl.file_set.selected_stance_details.append(2)
                    if stance_leg_ik_datas[0] == 1:
                        self.frame.file_panel_ctrl.file_set.selected_stance_details.append(3)
                    if stance_toe_datas[0] == 1:
                        self.frame.file_panel_ctrl.file_set.selected_stance_details.append(4)
                    if stance_toe_ik_datas[0] == 1:
                        self.frame.file_panel_ctrl.file_set.selected_stance_details.append(5)
                    if stance_shoulder_datas[0] == 1:
                        self.frame.file_panel_ctrl.file_set.selected_stance_details.append(6)
                    if stance_center_y_datas[0] == 1:
                        self.frame.file_panel_ctrl.file_set.selected_stance_details.append(7)

                    # 捩り分散
                    self.frame.file_panel_ctrl.file_set.rep_model_file_ctrl.title_parts_ctrl.SetValue(separate_twist_datas[0])

                    # 腕체크스킵
                    self.frame.arm_panel_ctrl.arm_check_skip_flg_ctrl.SetValue(arm_check_skip_datas[0])

                    # 모프データ
                    self.frame.morph_panel_ctrl.bulk_morph_set_dict[1] = []
                    for morph_data in morph_datas:
                        m = re.findall(r"([^\:]+)\:([^\:]+)\:(\d+\.?\d*)\;", morph_data)
                        self.frame.morph_panel_ctrl.bulk_morph_set_dict[1].append((m[0][0], m[0][1], float(m[0][2])))

                    # 接触回避
                    self.frame.arm_panel_ctrl.arm_process_flg_avoidance.SetValue(arm_avoidance_datas[0])

                    # 接触回避データ
                    self.frame.arm_panel_ctrl.bulk_avoidance_set_dict[0] = []
                    for avoidance_data in avoidance_name_datas:
                        m = re.findall(r"([^\:]+)\;", avoidance_data)
                        self.frame.arm_panel_ctrl.bulk_avoidance_set_dict[0].append(m[0][0])

                    # 위치 맞춤
                    self.frame.arm_panel_ctrl.arm_process_flg_alignment.SetValue(arm_alignment_datas[0])
                    self.frame.arm_panel_ctrl.arm_alignment_finger_flg_ctrl.SetValue(finger_alignment_datas[0])
                    self.frame.arm_panel_ctrl.arm_alignment_floor_flg_ctrl.SetValue(floor_alignment_datas[0])

                    # 위치 맞춤거리
                    self.frame.arm_panel_ctrl.alignment_distance_wrist_slider.SetValue(arm_alignment_length_datas)
                    self.frame.arm_panel_ctrl.alignment_distance_finger_slider.SetValue(finger_alignment_length_datas)
                    self.frame.arm_panel_ctrl.alignment_distance_floor_slider.SetValue(floor_alignment_length_datas)

                    # 移動量보정値
                    self.frame.leg_panel_ctrl.move_correction_slider.SetValue(move_correction_data)

                    # 足ＩＫオフセット
                    self.frame.leg_panel_ctrl.bulk_leg_offset_set_dict[0] = leg_offset_data

                    # 카메라
                    self.frame.camera_panel_ctrl.camera_vmd_file_ctrl.file_ctrl.SetPath(org_camera_motion_path)
                    self.frame.camera_panel_ctrl.output_camera_vmd_file_ctrl.file_ctrl.SetPath("")
                    self.frame.camera_panel_ctrl.camera_length_slider.SetValue(camera_length_datas)

                    # 카메라元情報
                    self.frame.camera_panel_ctrl.initialize(event)
                    self.frame.camera_panel_ctrl.camera_set_dict[1].camera_model_file_ctrl.file_ctrl.SetPath(org_camera_model_path)
                    self.frame.camera_panel_ctrl.camera_set_dict[1].camera_offset_y_ctrl.SetValue(camera_y_offset_datas)

                    # 出力パス変更
                    self.frame.file_panel_ctrl.file_set.set_output_vmd_path(event)
                    self.frame.camera_panel_ctrl.set_output_vmd_path(event)
                else:
                    # 複数パネルセット追加
                    self.frame.multi_panel_ctrl.on_add_set(event)

                    # ファイルパネル設定
                    self.frame.multi_panel_ctrl.file_set_list[now_motion_idx - 1].motion_vmd_file_ctrl.file_ctrl.SetPath(org_motion_path)
                    self.frame.multi_panel_ctrl.file_set_list[now_motion_idx - 1].org_model_file_ctrl.file_ctrl.SetPath(org_model_path)
                    self.frame.multi_panel_ctrl.file_set_list[now_motion_idx - 1].rep_model_file_ctrl.file_ctrl.SetPath(rep_model_path)
                    self.frame.multi_panel_ctrl.file_set_list[now_motion_idx - 1].output_vmd_file_ctrl.file_ctrl.SetPath("")

                    self.frame.multi_panel_ctrl.file_set_list[now_motion_idx - 1].org_model_file_ctrl.title_parts_ctrl.SetValue(
                        stance_center_xz_datas[0] | stance_upper_datas[0] | stance_lower_datas[0] | stance_leg_ik_datas[0] | \
                        stance_toe_datas[0] | stance_toe_ik_datas[0] | stance_shoulder_datas[0] | stance_center_y_datas[0]
                    )

                    # スタンス追加보정
                    self.frame.multi_panel_ctrl.file_set_list[now_motion_idx - 1].selected_stance_details = []
                    if stance_center_xz_datas[0] == 1:
                        self.frame.multi_panel_ctrl.file_set_list[now_motion_idx - 1].selected_stance_details.append(0)
                    if stance_upper_datas[0] == 1:
                        self.frame.multi_panel_ctrl.file_set_list[now_motion_idx - 1].selected_stance_details.append(1)
                    if stance_lower_datas[0] == 1:
                        self.frame.multi_panel_ctrl.file_set_list[now_motion_idx - 1].selected_stance_details.append(2)
                    if stance_leg_ik_datas[0] == 1:
                        self.frame.multi_panel_ctrl.file_set_list[now_motion_idx - 1].selected_stance_details.append(3)
                    if stance_toe_datas[0] == 1:
                        self.frame.multi_panel_ctrl.file_set_list[now_motion_idx - 1].selected_stance_details.append(4)
                    if stance_toe_ik_datas[0] == 1:
                        self.frame.multi_panel_ctrl.file_set_list[now_motion_idx - 1].selected_stance_details.append(5)
                    if stance_shoulder_datas[0] == 1:
                        self.frame.multi_panel_ctrl.file_set_list[now_motion_idx - 1].selected_stance_details.append(6)
                    if stance_center_y_datas[0] == 1:
                        self.frame.multi_panel_ctrl.file_set_list[now_motion_idx - 1].selected_stance_details.append(7)

                    # 捩り分散
                    self.frame.multi_panel_ctrl.file_set_list[now_motion_idx - 1].rep_model_file_ctrl.title_parts_ctrl.SetValue(separate_twist_datas[0])

                    # 모프データ
                    self.frame.morph_panel_ctrl.bulk_morph_set_dict[now_motion_idx + 1] = []
                    for morph_data in morph_datas:
                        m = re.findall(r"([^\:]+)\:([^\:]+)\:(\d+\.?\d*)\;", morph_data)
                        self.frame.morph_panel_ctrl.bulk_morph_set_dict[now_motion_idx + 1].append((m[0][0], m[0][1], float(m[0][2])))

                    # 接触回避データ
                    self.frame.arm_panel_ctrl.bulk_avoidance_set_dict[now_motion_idx - 1] = []
                    for avoidance_data in avoidance_name_datas:
                        m = re.findall(r"([^\:]+)\;", avoidance_data)
                        self.frame.arm_panel_ctrl.bulk_avoidance_set_dict[now_motion_idx - 1].append(m[0][0])

                    # 足ＩＫオフセット
                    self.frame.leg_panel_ctrl.bulk_leg_offset_set_dict[now_motion_idx - 1] = leg_offset_data

                    # 指위치 맞춤は常に0(ダイアログ防止)
                    self.frame.arm_panel_ctrl.arm_alignment_finger_flg_ctrl.SetValue(0)

                    # 카메라元情報
                    self.frame.camera_panel_ctrl.initialize(event)
                    self.frame.camera_panel_ctrl.camera_set_dict[now_motion_idx + 1].camera_model_file_ctrl.file_ctrl.SetPath(org_camera_model_path)
                    self.frame.camera_panel_ctrl.camera_set_dict[now_motion_idx + 1].camera_offset_y_ctrl.SetValue(camera_y_offset_datas)

                    # 出力パス変更
                    self.frame.multi_panel_ctrl.file_set_list[now_motion_idx - 1].set_output_vmd_path(event)

        if not is_buld:
            # Bulk終了
            self.finish_buld()

            return

        # 一旦リリース
        self.frame.release_tab()
        # ファイルタブに移動
        self.frame.note_ctrl.ChangeSelection(self.frame.file_panel_ctrl.tab_idx)
        # フォーム無効化
        self.frame.file_panel_ctrl.disable()
        # タブ固定
        self.frame.file_panel_ctrl.fix_tab()

        # ファイルタブのコンソール
        sys.stdout = self.frame.file_panel_ctrl.console_ctrl

        self.frame.elapsed_time = 0
        result = True
        result = self.frame.is_valid() and result

        if not result:
            # タブ移動可
            self.frame.release_tab()
            # フォーム有効化
            self.frame.enable()

            return result

        # 読み込み開始
        if self.frame.load_worker:
            logger.error("아직 처리가 진행 중입니다. 종료후 다시 실행해 주세요.", decoration=MLogger.DECORATION_BOX)
        else:
            # 停止ボタンに切り替え
            self.frame.file_panel_ctrl.check_btn_ctrl.SetLabel("읽기 처리 정지")
            self.frame.file_panel_ctrl.check_btn_ctrl.Enable()

            # 別スレッドで実行(次行がない場合、-1で終了フラグ)
            self.frame.load_worker = LoadWorkerThread(self.frame, BulkLoadThreadEvent, row_no if row_no > line_idx else -1, True, False, False, False)
            self.frame.load_worker.start()

        return result

    # 読み込み完了処理
    def on_load_result(self, event: wx.Event):
        self.frame.elapsed_time = event.elapsed_time

        # タブ移動可
        self.frame.release_tab()
        # フォーム有効化
        self.frame.enable()
        # ワーカー終了
        self.frame.load_worker = None
        # プログレス非表示
        self.frame.file_panel_ctrl.gauge_ctrl.SetValue(0)

        if not event.result:
            # 終了音を鳴らす
            self.frame.sound_finish()

            event.Skip()
            return False

        result = self.frame.is_loaded_valid()

        if not result:
            # タブ移動可
            self.frame.release_tab()
            # フォーム有効化
            self.frame.enable()

            event.Skip()
            return False

        logger.info("파일 데이터 읽기가 완료되었습니다.", decoration=MLogger.DECORATION_BOX, title="OK")

        # フォーム無効化
        self.frame.file_panel_ctrl.disable()
        # タブ固定
        self.frame.file_panel_ctrl.fix_tab()

        if self.frame.worker:
            logger.error("아직 처리가 진행 중입니다.종료 후 다시 실행해 주세요.", decoration=MLogger.DECORATION_BOX)
        else:
            # 停止ボタンに切り替え
            self.frame.file_panel_ctrl.exec_btn_ctrl.SetLabel("VMD 사이징 정지")
            self.frame.file_panel_ctrl.exec_btn_ctrl.Enable()

            # 別スレッドで実行
            self.frame.worker = SizingWorkerThread(self.frame, BulkSizingThreadEvent, event.target_idx, self.frame.is_saving, self.frame.is_out_log)
            self.frame.worker.start()

    # スレッド実行結果
    def on_exec_result(self, event: wx.Event):
        # 実行ボタンに切り替え
        self.frame.file_panel_ctrl.exec_btn_ctrl.SetLabel("VMD 사이징 실행")
        self.frame.file_panel_ctrl.exec_btn_ctrl.Enable()

        if not event.result:
            # 終了音を鳴らす
            self.frame.sound_finish()

            event.Skip()
            return False

        self.frame.elapsed_time += event.elapsed_time
        worked_time = "\n처리 시간: {0}".format(self.frame.show_worked_time())
        logger.info(worked_time)

        if self.frame.is_out_log and event.output_log_path and os.path.exists(event.output_log_path):
            # ログ出力対象である場合、追記
            with open(event.output_log_path, mode='a', encoding='utf-8') as f:
                f.write(worked_time)

        # ワーカー終了
        self.frame.worker = None

        if event.target_idx >= 0:
            # 次のターゲットがある場合、次を処理
            logger.info("\n----------------------------------")

            return self.load(event, event.target_idx + 1)

        # Bulk終了
        self.finish_buld()

    def finish_buld(self):
        # ファイルタブのコンソール
        sys.stdout = self.frame.file_panel_ctrl.console_ctrl

        # 終了音を鳴らす
        self.frame.sound_finish()

        # ファイルタブのコンソール
        if sys.stdout != self.frame.file_panel_ctrl.console_ctrl:
            sys.stdout = self.frame.file_panel_ctrl.console_ctrl

        # Bulk用データ消去
        self.frame.morph_panel_ctrl.bulk_morph_set_dict = {}
        self.frame.arm_panel_ctrl.bulk_avoidance_set_dict = {}
        self.frame.camera_panel_ctrl.bulk_camera_set_dict = {}

        # タブ移動可
        self.frame.release_tab()
        # フォーム有効化
        self.frame.enable()
        # プログレス非表示
        self.frame.file_panel_ctrl.gauge_ctrl.SetValue(0)

        logger.info("모든 사이징 처리가 끝났습니다.", decoration=MLogger.DECORATION_BOX, title="일괄 처리")
