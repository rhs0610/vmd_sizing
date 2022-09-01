# -*- coding: utf-8 -*-
#
import wx
import wx.lib.newevent
import sys

from form.panel.BasePanel import BasePanel
from form.parts.BaseFilePickerCtrl import BaseFilePickerCtrl
from form.parts.ConsoleCtrl import ConsoleCtrl
from form.worker.VmdWorkerThread import VmdWorkerThread
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from utils import MFormUtils, MFileUtils # noqa
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)

# イベント定義
(VmdThreadEvent, EVT_VMD_THREAD) = wx.lib.newevent.NewEvent()


class VmdPanel(BasePanel):

    def __init__(self, frame: wx.Frame, parent: wx.Notebook, tab_idx: int):
        super().__init__(frame, parent, tab_idx)
        self.convert_vmd_worker = None

        self.description_txt = wx.StaticText(self, wx.ID_ANY, "지정된 CSV 파일(본+모프 or 카메라)을 VMD파일로 출력합니다.\n" \
                                             + "모델 모션（본+모프)과 카메라 모션（카메라）을 따로 출력할 수 있습니다.\n" \
                                             + "CSV의 포맷은、CSV탭에서 출력한 데이터와 같은 것을 정의해 주세요.", wx.DefaultPosition, wx.DefaultSize, 0)
        self.sizer.Add(self.description_txt, 0, wx.ALL, 5)

        self.static_line = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.sizer.Add(self.static_line, 0, wx.EXPAND | wx.ALL, 5)

        # CSV파일コントロール（본）
        self.bone_csv_file_ctrl = BaseFilePickerCtrl(frame, self, u"CSV파일（본）", u"CSV파일을 선택해 주세요", ("csv"), wx.FLP_DEFAULT_STYLE, \
                                                     u"VMD로 변환하고자 하는 본모션의 파일 경로를 지정하십시오.", \
                                                     is_aster=False, is_save=False, set_no=0, required=False)
        self.sizer.Add(self.bone_csv_file_ctrl.sizer, 0, wx.EXPAND | wx.ALL, 0)

        # CSV파일コントロール（모프）
        self.morph_csv_file_ctrl = BaseFilePickerCtrl(frame, self, u"CSV파일（모프）", u"CSV파일을 선택해 주세요", ("csv"), wx.FLP_DEFAULT_STYLE, \
                                                      u"VMD로 변환하고자 하는 모프 모션의 파일 경로를 지정하십시오.", \
                                                      is_aster=False, is_save=False, set_no=0, required=False)
        self.sizer.Add(self.morph_csv_file_ctrl.sizer, 0, wx.EXPAND | wx.ALL, 0)

        self.static_line2 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.sizer.Add(self.static_line2, 0, wx.EXPAND | wx.ALL, 5)

        # CSV파일コントロール（카메라）
        self.camera_csv_file_ctrl = BaseFilePickerCtrl(frame, self, u"CSV파일（카메라）", u"CSV파일파일을 선택해 주세요", ("csv"), wx.FLP_DEFAULT_STYLE, \
                                                       u"MD로 변환하고자 하는 카메라 모션의 파일 경로를 지정하십시오.", \
                                                       is_aster=False, is_save=False, set_no=0, required=False)
        self.sizer.Add(self.camera_csv_file_ctrl.sizer, 0, wx.EXPAND | wx.ALL, 0)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # VMD変換実行ボタン
        self.vmd_btn_ctrl = wx.Button(self, wx.ID_ANY, u"VMD변환 실행", wx.DefaultPosition, wx.Size(200, 50), 0)
        self.vmd_btn_ctrl.SetToolTip(u"CSV를 VMD로 변환합니다.")
        self.vmd_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_convert_vmd)
        btn_sizer.Add(self.vmd_btn_ctrl, 0, wx.ALL, 5)

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

        # フレームに変換完了処理バインド
        self.frame.Bind(EVT_VMD_THREAD, self.on_convert_vmd_result)

    # フォーム無効化
    def disable(self):
        self.bone_csv_file_ctrl.disable()
        self.morph_csv_file_ctrl.disable()
        self.camera_csv_file_ctrl.disable()
        self.vmd_btn_ctrl.Disable()

    # フォーム無効化
    def enable(self):
        self.bone_csv_file_ctrl.enable()
        self.morph_csv_file_ctrl.enable()
        self.camera_csv_file_ctrl.enable()
        self.vmd_btn_ctrl.Enable()

    # VMD変換
    def on_convert_vmd(self, event: wx.Event):
        # フォーム無効化
        self.disable()
        # 탭固定
        self.fix_tab()
        # コンソールクリア
        self.console_ctrl.Clear()
        # 출력先をVMDパネルのコンソールに変更
        sys.stdout = self.console_ctrl

        wx.GetApp().Yield()

        self.elapsed_time = 0
        result = True
        result = self.bone_csv_file_ctrl.is_valid() and result

        if not result:
            # 終了音
            self.frame.sound_finish()
            # 탭移動可
            self.release_tab()
            # フォーム有効化
            self.enable()
            # 출력先をデフォルトに戻す
            if sys.stdout != self.frame.file_panel_ctrl.console_ctrl:
                sys.stdout = self.frame.file_panel_ctrl.console_ctrl

            return result

        # VMD変換開始
        if self.convert_vmd_worker:
            logger.error("아직 처리가 진행 중입니다. 종료 후 다시 실행해 주세요.", decoration=MLogger.DECORATION_BOX)
        else:
            # 別スレッドで実行
            self.convert_vmd_worker = VmdWorkerThread(self.frame, VmdThreadEvent)
            self.convert_vmd_worker.start()

        return result

        event.Skip()

    # VMD変換完了処理
    def on_convert_vmd_result(self, event: wx.Event):
        self.elapsed_time = event.elapsed_time

        # 終了音
        self.frame.sound_finish()

        # 탭移動可
        self.release_tab()
        # フォーム有効化
        self.enable()
        # ワーカー終了
        self.convert_vmd_worker = None
        # プログレス非表示
        self.gauge_ctrl.SetValue(0)

        if not event.result:
            logger.error("VMD변환 처리에 실패했습니다.", decoration=MLogger.DECORATION_BOX)

            event.Skip()
            return False

        logger.info("VMD변환이 완료되었습니다.", decoration=MLogger.DECORATION_BOX, title="OK")

        # 출력先をデフォルトに戻す
        if sys.stdout != self.frame.file_panel_ctrl.console_ctrl:
            sys.stdout = self.frame.file_panel_ctrl.console_ctrl

