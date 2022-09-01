# -*- coding: utf-8 -*-
#
import os
import sys
import wx
import threading

from form.panel.FilePanel import FilePanel
from form.panel.MorphPanel import MorphPanel
from form.panel.MultiPanel import MultiPanel
from form.panel.ArmPanel import ArmPanel
from form.panel.LegPanel import LegPanel
from form.panel.CameraPanel import CameraPanel
from form.panel.CsvPanel import CsvPanel
from form.panel.VmdPanel import VmdPanel
from form.panel.BulkPanel import BulkPanel
from form.worker.SizingWorkerThread import SizingWorkerThread
from form.worker.LoadWorkerThread import LoadWorkerThread
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4  # noqa
from utils import MFormUtils, MFileUtils  # noqa
from utils.MLogger import MLogger  # noqa

if os.name == "nt":
    import winsound  # Windows版のみインポート

logger = MLogger(__name__)


# Invent
(SizingThreadEvent, EVT_SIZING_THREAD) = wx.lib.newevent.NewEvent()
(LoadThreadEvent, EVT_LOAD_THREAD) = wx.lib.newevent.NewEvent()


class MainFrame(wx.Frame):
    def __init__(
        self, parent, mydir_path: str, version_name: str, logging_level: int, is_saving: bool, is_out_log: bool
    ):
        self.version_name = version_name
        self.logging_level = logging_level
        self.is_out_log = is_out_log
        self.is_saving = is_saving
        self.mydir_path = mydir_path
        self.elapsed_time = 0
        self.popuped_finger_warning = False

        self.worker = None
        self.load_worker = None

        wx.Frame.__init__(
            self,
            parent,
            id=wx.ID_ANY,
            title="VMD 사이징 로컬 판 {0}".format(self.version_name),
            pos=wx.DefaultPosition,
            size=wx.Size(600, 650),
            style=wx.DEFAULT_FRAME_STYLE | wx.TAB_TRAVERSAL,
        )

        # File history read
        self.file_hitories = MFileUtils.read_history(self.mydir_path)

        # ---------------------------------------------

        self.SetSizeHints(wx.DefaultSize, wx.DefaultSize)

        bSizer1 = wx.BoxSizer(wx.VERTICAL)

        self.note_ctrl = wx.Notebook(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, 0)
        if self.logging_level == MLogger.FULL or self.logging_level == MLogger.DEBUG_FULL:
            # Full Data Case
            self.note_ctrl.SetBackgroundColour("RED")
        elif self.logging_level == MLogger.DEBUG:
            # Test(Debug Version) Case
            self.note_ctrl.SetBackgroundColour("CORAL")
        elif self.logging_level == MLogger.TIMER:
            # Time Measurement Case
            self.note_ctrl.SetBackgroundColour("YELLOW")
        elif not is_saving:
            # Log Existence Case -> Change Color
            self.note_ctrl.SetBackgroundColour("BLUE")
        elif is_out_log:
            # Log Existence Case -> Change Color
            self.note_ctrl.SetBackgroundColour("AQUAMARINE")
        else:
            self.note_ctrl.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNSHADOW))

        # ---------------------------------------------

        # File Tab
        self.file_panel_ctrl = FilePanel(self, self.note_ctrl, 0, self.file_hitories)
        self.note_ctrl.AddPage(self.file_panel_ctrl, "파일", True)

        # Multile Tab
        self.multi_panel_ctrl = MultiPanel(self, self.note_ctrl, 1, self.file_hitories)
        self.note_ctrl.AddPage(self.multi_panel_ctrl, "복수", False)

        # Morph Tab
        self.morph_panel_ctrl = MorphPanel(self, self.note_ctrl, 2)
        self.note_ctrl.AddPage(self.morph_panel_ctrl, "모프", False)

        # Arm Tab
        self.arm_panel_ctrl = ArmPanel(self, self.note_ctrl, 3)
        self.note_ctrl.AddPage(self.arm_panel_ctrl, "팔", False)

        # Foot Tab
        self.leg_panel_ctrl = LegPanel(self, self.note_ctrl, 4)
        self.note_ctrl.AddPage(self.leg_panel_ctrl, "발", False)

        # Camera Tab
        self.camera_panel_ctrl = CameraPanel(self, self.note_ctrl, 5)
        self.note_ctrl.AddPage(self.camera_panel_ctrl, "카메라", False)

        # Entire Tab
        self.bulk_panel_ctrl = BulkPanel(self, self.note_ctrl, 6)
        self.note_ctrl.AddPage(self.bulk_panel_ctrl, "일괄", False)

        # CSV Tab
        self.csv_panel_ctrl = CsvPanel(self, self.note_ctrl, 7)
        self.note_ctrl.AddPage(self.csv_panel_ctrl, "CSV", False)

        # VMD Tab
        self.vmd_panel_ctrl = VmdPanel(self, self.note_ctrl, 8)
        self.note_ctrl.AddPage(self.vmd_panel_ctrl, "VMD", False)

        # ---------------------------------------------

        # Process when pressing tab
        self.note_ctrl.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_change)

        # ---------------------------------------------

        bSizer1.Add(self.note_ctrl, 1, wx.EXPAND, 5)

        # Default showing tab = file output tab
        sys.stdout = self.file_panel_ctrl.console_ctrl

        # Event Bind
        self.Bind(EVT_SIZING_THREAD, self.on_exec_result)
        self.Bind(EVT_LOAD_THREAD, self.on_load_result)

        self.SetSizer(bSizer1)
        self.Layout()

        self.Centre(wx.BOTH)

    def on_idle(self, event: wx.Event):
        if self.worker or self.load_worker:
            self.file_panel_ctrl.gauge_ctrl.Pulse()
        elif self.csv_panel_ctrl.convert_csv_worker:
            self.csv_panel_ctrl.gauge_ctrl.Pulse()
        elif self.vmd_panel_ctrl.convert_vmd_worker:
            self.vmd_panel_ctrl.gauge_ctrl.Pulse()

    def on_tab_change(self, event: wx.Event):
        # Return to File Tab Console
        sys.stdout = self.file_panel_ctrl.console_ctrl

        if self.file_panel_ctrl.is_fix_tab:
            self.note_ctrl.ChangeSelection(self.file_panel_ctrl.tab_idx)
            event.Skip()
            return

        elif self.morph_panel_ctrl.is_fix_tab:
            # If morph tab is fixed to file tab, fixed tab is file tab
            self.note_ctrl.ChangeSelection(self.file_panel_ctrl.tab_idx)
            event.Skip()
            return

        elif self.arm_panel_ctrl.is_fix_tab:
            # If morph tab is fixed to arm tab, fixed tab is arm tab
            self.note_ctrl.ChangeSelection(self.file_panel_ctrl.tab_idx)
            event.Skip()
            return

        elif self.csv_panel_ctrl.is_fix_tab:
            self.note_ctrl.ChangeSelection(self.csv_panel_ctrl.tab_idx)
            event.Skip()
            return

        elif self.vmd_panel_ctrl.is_fix_tab:
            self.note_ctrl.ChangeSelection(self.vmd_panel_ctrl.tab_idx)
            event.Skip()
            return

        elif self.bulk_panel_ctrl.is_fix_tab:
            self.note_ctrl.ChangeSelection(self.bulk_panel_ctrl.tab_idx)
            event.Skip()
            return

        if self.note_ctrl.GetSelection() == self.multi_panel_ctrl.tab_idx:
            # If Using Multiple Tab, Save
            self.file_panel_ctrl.save()

        if self.note_ctrl.GetSelection() == self.morph_panel_ctrl.tab_idx:
            # Console Clear
            self.file_panel_ctrl.console_ctrl.Clear()
            wx.GetApp().Yield()

            # File tab fix first
            self.note_ctrl.SetSelection(self.file_panel_ctrl.tab_idx)
            self.morph_panel_ctrl.fix_tab()

            logger.info("모프 탭 표시 준비 시작\n파일 로드 처리를 실행합니다. 조금 기다려주세요....", decoration=MLogger.DECORATION_BOX)

            # Read process execution
            self.load(event, target_idx=0, is_morph=True)

        if self.note_ctrl.GetSelection() == self.arm_panel_ctrl.tab_idx:
            # Console Clear
            self.file_panel_ctrl.console_ctrl.Clear()
            wx.GetApp().Yield()

            # File tab fix first
            self.note_ctrl.SetSelection(self.file_panel_ctrl.tab_idx)
            self.arm_panel_ctrl.fix_tab()

            logger.info("팔 탭 표시 준비 시작\n파일 로드 처리를 실행합니다. 조금 기다려주세요 ....", decoration=MLogger.DECORATION_BOX)

            # Read process execution
            self.load(event, target_idx=0, is_arm=True)

        if self.note_ctrl.GetSelection() == self.leg_panel_ctrl.tab_idx:
            # Console Clear
            self.file_panel_ctrl.console_ctrl.Clear()
            wx.GetApp().Yield()

            # File tab fix first
            self.note_ctrl.SetSelection(self.file_panel_ctrl.tab_idx)
            self.leg_panel_ctrl.fix_tab()

            logger.info("발 탭 표시 준비 시작\n파일 로드 처리를 실행합니다. 조금 기다려주세요 ....", decoration=MLogger.DECORATION_BOX)

            # Read process execution
            self.load(event, target_idx=0, is_leg=True)

        if self.note_ctrl.GetSelection() == self.camera_panel_ctrl.tab_idx:
            # If Camera tab is opened, Camera tab initialize
            self.note_ctrl.ChangeSelection(self.camera_panel_ctrl.tab_idx)
            self.camera_panel_ctrl.initialize(event)

    # Switching tab available
    def release_tab(self):
        self.file_panel_ctrl.release_tab()
        self.morph_panel_ctrl.release_tab()
        self.arm_panel_ctrl.release_tab()
        self.multi_panel_ctrl.release_tab()
        self.bulk_panel_ctrl.release_tab()

    # From input available
    def enable(self):
        self.file_panel_ctrl.enable()
        self.bulk_panel_ctrl.enable()

    # File set input check
    def is_valid(self):
        result = True
        result = self.file_panel_ctrl.file_set.is_valid() and result

        # multi
        for file_set in self.multi_panel_ctrl.file_set_list:
            result = file_set.is_valid() and result

        return result

    # Input after input check
    def is_loaded_valid(self):
        result = True
        result = self.file_panel_ctrl.file_set.is_loaded_valid() and result

        # How many multi?
        for file_set in self.multi_panel_ctrl.file_set_list:
            result = file_set.is_loaded_valid() and result

        # If only camera sizing is checked, check where is camera file path and sizing data
        if self.camera_panel_ctrl.camera_only_flg_ctrl.GetValue():
            if not self.camera_panel_ctrl.camera_vmd_file_ctrl.data:
                logger.error("카메라 사이징만 실행할 경우, \n카메라 VMD 데이터를 지정하십시오.", decoration=MLogger.DECORATION_BOX)
                result = False

            if not (
                os.path.exists(self.file_panel_ctrl.file_set.output_vmd_file_ctrl.path())
                and os.path.isfile(self.file_panel_ctrl.file_set.output_vmd_file_ctrl.path())
            ):
                logger.error(
                    "카메라 사이징만 실행할 경우, \n1번째 파일셋 출력 VMD에는 기존 사이징이 완료된 VMD 파일 경로를 지정해야 합니다."
                    "\n（출력 VMD를 '열기'에서 지정한 경우에 '덧어쓰겠겠습니까?'라고 경고가 나오지만 실제로는 덮어쓰기는 하지 않습니다.）",
                    decoration=MLogger.DECORATION_BOX,
                )
                result = False

            for fidx, file_set in enumerate(self.multi_panel_ctrl.file_set_list):
                if not (
                    os.path.exists(file_set.output_vmd_file_ctrl.path())
                    and os.path.isfile(file_set.output_vmd_file_ctrl.path())
                ):
                    logger.error(
                        f"카메라 사이징만 실행할 경우, \n{fidx+1}번째 파일 세트의 출력 VMD에는 기존 사이징이 완료된 VMD 파일 경로를 지정해야 합니다."
                        "\n（출력 VMD를 '열기'에서 지정한 경우에 '덧어쓰겠겠습니까?'라고 경고가 나오지만 실제로는 덮어쓰기는 하지 않습니다.））",
                        decoration=MLogger.DECORATION_BOX,
                    )
                    result = False

        return result

    def show_worked_time(self):
        # Change Elapsed second to Hour, Minute, Second
        td_m, td_s = divmod(self.elapsed_time, 60)

        if td_m == 0:
            worked_time = "{0:02d}초".format(int(td_s))
        else:
            worked_time = "{0:02d}분{1:02d}초".format(int(td_m), int(td_s))

        return worked_time

    # Path of File tab's Processing file
    def get_target_vmd_path(self, target_idx):
        if self.file_panel_ctrl.file_set.motion_vmd_file_ctrl.astr_path:
            if len(self.file_panel_ctrl.file_set.motion_vmd_file_ctrl.target_paths) > target_idx:
                return self.file_panel_ctrl.file_set.motion_vmd_file_ctrl.target_paths[target_idx]
            else:
                return None

        return self.file_panel_ctrl.file_set.motion_vmd_file_ctrl.file_ctrl.GetPath()

    # 読み込み
    def load(self, event, target_idx, is_exec=False, is_morph=False, is_arm=False, is_leg=False):
        # form deactivation
        self.file_panel_ctrl.disable()
        # tab fixation
        self.file_panel_ctrl.fix_tab()

        self.elapsed_time = 0
        result = True
        result = self.is_valid() and result

        if not result:
            if is_morph or is_arm or is_leg:
                tab_name = "모프" if is_morph else "팔" if is_arm else "발"
                # 読み込み出来なかったらエラー
                logger.error(
                    "파일 탭에서 다음 중 하나의 파일 경로가 지정되지 않아 {tab_name} 탭을 열 수 없습니다.".format(tab_name=tab_name)
                    + "\n · 조정대상 VMD파일"
                    + "\n · 작성 원본 모델 PMX 파일"
                    + "\n · 변환 원본 모델 PMX 파일"
                    + "\n 이미 지정된 경우 현재 읽기 중일 수 있습니다."
                    + "\n 특히 긴 VMD는 읽기에 시간이 걸립니다."
                    + "\n 조정에 필요한 3가지 파일을 모두 지정하여"
                    + "\n '■ 읽기 성공' 로그가 나온 후 '{tab_name}' 탭을 열어주세요.".format(tab_name=tab_name),
                    decoration=MLogger.DECORATION_BOX,
                )

            # Tab switching available
            self.release_tab()
            # Form Activation
            self.enable()

            return result

        # Read start
        if self.load_worker:
            logger.error("아직 처리가 진행 중입니다.종료 후 다시 실행해 주세요.", decoration=MLogger.DECORATION_BOX)
        else:
            # Set actual value Processing VMD/VPD file of File tab
            target_path = self.get_target_vmd_path(target_idx)
            self.file_panel_ctrl.file_set.motion_vmd_file_ctrl.file_ctrl.SetPath(target_path)
            self.file_panel_ctrl.file_set.motion_vmd_file_ctrl.file_model_ctrl.set_model(target_path)
            # Output path change
            if not self.file_panel_ctrl.file_set.output_vmd_file_ctrl.file_ctrl.GetPath() or target_idx > 0:
                self.file_panel_ctrl.file_set.output_vmd_file_ctrl.file_ctrl.SetPath("")
                self.file_panel_ctrl.file_set.set_output_vmd_path(event)

            # Switch to stop button
            self.file_panel_ctrl.check_btn_ctrl.SetLabel("읽기 처리 정지")
            self.file_panel_ctrl.check_btn_ctrl.Enable()

            # Process in another thread
            self.load_worker = LoadWorkerThread(self, LoadThreadEvent, target_idx, is_exec, is_morph, is_arm, is_leg)
            self.load_worker.start()

        return result

    # Loading finish
    def on_load_result(self, event: wx.Event):
        self.elapsed_time = event.elapsed_time

        # Tab Switch available
        self.release_tab()
        # Form Activation
        self.enable()
        # End Worker
        self.load_worker = None
        # Hide Progress
        self.file_panel_ctrl.gauge_ctrl.SetValue(0)

        # Change to chect button
        self.file_panel_ctrl.check_btn_ctrl.SetLabel("변환 전 체크")
        self.file_panel_ctrl.check_btn_ctrl.Enable()

        if not event.result:
            # Finish Sound
            self.sound_finish()

            event.Skip()
            return False

        result = self.is_loaded_valid()

        if not result:
            # Finish Sound
            self.sound_finish()
            # Switching tab available
            self.release_tab()
            # Form activation
            self.enable()

            event.Skip()
            return False

        logger.info("파일 데이터 읽기 완료.", decoration=MLogger.DECORATION_BOX, title="OK")

        if event.is_exec:
            # 그대로 실행할 경우 사이징 실행 처리로 전이

            # 만약을 위해 출력 파일 경로 자동 생성(빈 경우 설정)
            if not self.file_panel_ctrl.file_set.output_vmd_file_ctrl.file_ctrl.GetPath():
                self.file_panel_ctrl.file_set.set_output_vmd_path(event)

            # multi의 출력 파일 경로 자동 생성(빈 경우 설정)
            for file_set in self.multi_panel_ctrl.file_set_list:
                if not file_set.output_vmd_file_ctrl.file_ctrl.GetPath():
                    file_set.set_output_vmd_path(event)

            # Form deactivation
            self.file_panel_ctrl.disable()
            # form fix
            self.file_panel_ctrl.fix_tab()

            if self.worker:
                logger.error("아직 처리가 진행 중입니다. 처리 종료 후 다시 실행해 주세요.", decoration=MLogger.DECORATION_BOX)
            else:
                # Change to stop button
                self.file_panel_ctrl.exec_btn_ctrl.SetLabel("VMD 사이징 정지")
                self.file_panel_ctrl.exec_btn_ctrl.Enable()

                # Process in Another thread
                self.worker = SizingWorkerThread(
                    self, SizingThreadEvent, event.target_idx, self.is_saving, self.is_out_log
                )
                self.worker.start()

        elif event.is_morph:
            # If open morph tab, initialize morph tab
            self.note_ctrl.ChangeSelection(self.morph_panel_ctrl.tab_idx)
            self.morph_panel_ctrl.initialize(event)

        elif event.is_arm:
            # If open arm tab, initialize arm tab
            self.note_ctrl.ChangeSelection(self.arm_panel_ctrl.tab_idx)
            self.arm_panel_ctrl.initialize(event)

        elif event.is_leg:
            # If open leg tab, initialize leg tab
            self.note_ctrl.ChangeSelection(self.leg_panel_ctrl.tab_idx)
            self.leg_panel_ctrl.initialize(event)

        else:
            # finish sound
            self.sound_finish()

            logger.info("\n처리시간: %s", self.show_worked_time())

            event.Skip()
            return True

    # Thread ececution result
    def on_exec_result(self, event: wx.Event):
        # change to process button
        self.file_panel_ctrl.exec_btn_ctrl.SetLabel("VMD사이징 실행")
        self.file_panel_ctrl.exec_btn_ctrl.Enable()

        self.elapsed_time += event.elapsed_time
        worked_time = "\n처리시간: {0}".format(self.show_worked_time())
        logger.info(worked_time)

        if self.is_out_log and event.output_log_path and os.path.exists(event.output_log_path):
            # If log out, record
            with open(event.output_log_path, mode="a", encoding="utf-8") as f:
                f.write(worked_time)

        logger.debug("self.worker = None")

        # Worker end
        self.worker = None

        if (
            event.result
            and self.file_panel_ctrl.file_set.motion_vmd_file_ctrl.astr_path
            and self.get_target_vmd_path(event.target_idx + 1)
        ):
            # If path with *, next existenca check
            logger.info("\n----------------------------------")

            return self.load(event, event.target_idx + 1, is_exec=True)

        # File tab console
        sys.stdout = self.file_panel_ctrl.console_ctrl

        # Finish sound
        self.sound_finish()

        # Switching tab avaiable
        self.release_tab()
        # Form activation
        self.enable()
        # Hide progress
        self.file_panel_ctrl.gauge_ctrl.SetValue(0)

    def sound_finish(self):
        threading.Thread(target=self.sound_finish_thread).start()

    def sound_finish_thread(self):
        # Finish sound
        if os.name == "nt":
            # Windows
            try:
                winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)
            except Exception:
                pass

    def on_wheel_spin_ctrl(self, event: wx.Event, inc=0.1):
        # if changing Spin control
        if event.GetWheelRotation() > 0:
            event.GetEventObject().SetValue(event.GetEventObject().GetValue() + inc)
            if event.GetEventObject().GetValue() >= 0:
                event.GetEventObject().SetBackgroundColour("WHITE")
        else:
            event.GetEventObject().SetValue(event.GetEventObject().GetValue() - inc)
            if event.GetEventObject().GetValue() < 0:
                event.GetEventObject().SetBackgroundColour("TURQUOISE")

    def on_popup_finger_warning(self, event: wx.Event):
        if not self.popuped_finger_warning:
            dialog = wx.MessageDialog(
                self,
                "복수 인원 모션으로 손가락 위치 맞춤이 ON되어 있습니다.\n손가락의 수만큼 조합이 방대해져서 시간이 걸리지만, "+"그에 비해 불필요한 손가락에 반응해서 깨끗해지지 않습니다.괜찮습니까?",
                style=wx.YES_NO | wx.ICON_WARNING,
            )
            if dialog.ShowModal() == wx.ID_NO:
                # 손가락 위치 맞춤OFF
                self.arm_panel_ctrl.arm_alignment_finger_flg_ctrl.SetValue(0)
                # 다시 손가락 위치 맞춤 ON
                self.arm_panel_ctrl.arm_process_flg_alignment.SetValue(1)

            dialog.Destroy()
            self.popuped_finger_warning = True
