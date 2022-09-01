# -*- coding: utf-8 -*-
#
import wx
import wx.lib.newevent

from form.panel.BasePanel import BasePanel
from form.parts.SizingFileSet import SizingFileSet
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from utils import MFileUtils # noqa
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)


class MultiPanel(BasePanel):

    def __init__(self, frame: wx.Frame, parent: wx.Notebook, tab_idx: int, file_hitories: dict):
        super().__init__(frame, parent, tab_idx)
        self.file_hitories = file_hitories

        self.header_panel = wx.Panel(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL)
        self.header_sizer = wx.BoxSizer(wx.VERTICAL)

        self.description_txt = wx.StaticText(self.header_panel, wx.ID_ANY, "여러 명 모션 등을 비율을 맞추어 사이징 할 수 있습니다. 2명째 이후를 지정하십시오." \
                                             + "\n축척을 강제로 바꾸고 있기 때문에 다리 등이 원래 모션에서 어긋나는 경우가 있습니다." \
                                             + "\n실수로 파일 세트를 추가해 버린 경우는, 4개의 파일란을 모두 비워 주세요.", wx.DefaultPosition, wx.DefaultSize, 0)
        self.header_sizer.Add(self.description_txt, 0, wx.ALL, 5)

        self.btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 파일세트클리어ボタン
        self.clear_btn_ctrl = wx.Button(self.header_panel, wx.ID_ANY, u"파일 세트 클리어", wx.DefaultPosition, wx.DefaultSize, 0)
        self.clear_btn_ctrl.SetToolTip(u"이미 입력된 데이터를 모두 비웁니다.")
        self.clear_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_clear_set)
        self.btn_sizer.Add(self.clear_btn_ctrl, 0, wx.ALL, 5)

        # 파일세트클리어ボタン
        self.add_btn_ctrl = wx.Button(self.header_panel, wx.ID_ANY, u"파일 세트 추가", wx.DefaultPosition, wx.DefaultSize, 0)
        self.add_btn_ctrl.SetToolTip(u"사이징에 필요한 파일세트를 패널에 추가합니다.")
        self.add_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_add_set)
        self.btn_sizer.Add(self.add_btn_ctrl, 0, wx.ALL, 5)

        self.header_sizer.Add(self.btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        self.header_panel.SetSizer(self.header_sizer)
        self.header_panel.Layout()
        self.sizer.Add(self.header_panel, 0, wx.EXPAND | wx.ALL, 5)

        # 파일세트
        self.file_set_list = []
        # 파일세트用基本Sizer
        self.set_base_sizer = wx.BoxSizer(wx.VERTICAL)

        self.scrolled_window = MultiFileSetScrolledWindow(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, \
                                                          wx.FULL_REPAINT_ON_RESIZE | wx.VSCROLL | wx.ALWAYS_SHOW_SB)
        # self.scrolled_window.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DLIGHT))
        # self.scrolled_window.SetBackgroundColour("BLUE")
        self.scrolled_window.SetScrollRate(5, 5)
        self.scrolled_window.set_file_set_list(self.file_set_list)

        self.scrolled_window.SetSizer(self.set_base_sizer)
        self.scrolled_window.Layout()
        self.sizer.Add(self.scrolled_window, 1, wx.ALL | wx.EXPAND | wx.FIXED_MINSIZE, 5)
        self.fit()

    def on_add_set(self, event: wx.Event):
        self.file_set_list.append(SizingFileSet(self.frame, self.scrolled_window, self.file_hitories, len(self.file_set_list) + 2))
        self.set_base_sizer.Add(self.file_set_list[-1].set_sizer, 0, wx.ALL, 5)
        self.set_base_sizer.Layout()

        # スクロールバーの表示のためにサイズ調整
        self.sizer.Layout()
        # self.sizer.FitInside(self.scrolled_window)

        if self.frame.arm_panel_ctrl.arm_alignment_finger_flg_ctrl.GetValue() and len(self.file_set_list) > 0:
            self.frame.on_popup_finger_warning(event)

        event.Skip()

    def on_clear_set(self, event: wx.Event):
        for file_set in self.file_set_list:
            file_set.motion_vmd_file_ctrl.file_ctrl.SetPath("")
            file_set.rep_model_file_ctrl.file_ctrl.SetPath("")
            file_set.org_model_file_ctrl.file_ctrl.SetPath("")
            file_set.output_vmd_file_ctrl.file_ctrl.SetPath("")

    # フォーム無効化
    def disable(self):
        self.file_set.disable()

    # フォーム無効化
    def enable(self):
        self.file_set.enable()


class MultiFileSetScrolledWindow(wx.ScrolledWindow):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

    def set_file_set_list(self, file_set_list):
        self.file_set_list = file_set_list

    def set_output_vmd_path(self, event, is_force=False):
        for file_set in self.file_set_list:
            file_set.set_output_vmd_path(event, is_force)

