# -*- coding: utf-8 -*-
#
import os
import wx

from form.panel.BasePanel import BasePanel
from form.parts.SizingFileSet import SizingFileSet
from form.parts.BaseFilePickerCtrl import BaseFilePickerCtrl
from form.parts.HistoryFilePickerCtrl import HistoryFilePickerCtrl
from form.parts.FloatSliderCtrl import FloatSliderCtrl
from utils import MFileUtils
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)


class CameraPanel(BasePanel):

    def __init__(self, frame: wx.Frame, parent: wx.Notebook, tab_idx: int):
        super().__init__(frame, parent, tab_idx)

        self.header_panel = CameraHeaderPanel(self.frame, self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL)
        self.header_sizer = wx.BoxSizer(wx.VERTICAL)

        self.description_txt = wx.StaticText(self.header_panel, wx.ID_ANY, u"지정된 카메라 모션의 사이징을, 본 모션의 사이징과 동시에 실시할 수 있습니다.\n" \
                                             + "전체 길이 오프닝 Y는 카메라에 비춘 변환용 모링의 전체 길이를 조정하는 오프셋 값을 지정할 수 있습니다. ", wx.DefaultPosition, wx.DefaultSize, 0)
        self.header_sizer.Add(self.description_txt, 0, wx.ALL, 5)

        self.static_line01 = wx.StaticLine(self.header_panel, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.header_sizer.Add(self.static_line01, 0, wx.EXPAND | wx.ALL, 5)

        camera_only_flg_spacer_ctrl = wx.StaticText(self.header_panel, wx.ID_ANY, u"　　　　　　　　　　　　　　　　　　　　　", wx.DefaultPosition, wx.DefaultSize, 0)

        # 카메라사이징のみ実行
        self.camera_only_flg_ctrl = wx.CheckBox(self.header_panel, wx.ID_ANY, u"카메라 사이징만을 실행", wx.DefaultPosition, wx.DefaultSize, 0)
        self.camera_only_flg_ctrl.SetToolTip(u"본 사이징이 끝난 파일을 출력 파일로 지정한 후 체크하면 \n 그 사이징이 끝난 VMD를 바탕으로 사이징을 실행합니다.")
        self.camera_only_flg_ctrl.Bind(wx.EVT_CHECKBOX, self.set_output_vmd_path)

        # 카메라VMD파일コントロール
        self.camera_vmd_file_ctrl = HistoryFilePickerCtrl(self.frame, self.header_panel, u"카메라 모션 VMD", u"카메라 모션 VMD 파일 을 엽니다", ("vmd"), wx.FLP_DEFAULT_STYLE, \
                                                          u"조정하고자 하는 카메라 모션의 VMD 경로를 지정하십시오.\nD&D에서의 지정, 열기 버튼에서의 지정, 이력에서의 선택을 할 수 있습니다.", \
                                                          file_model_spacer=0, title_parts_ctrl=camera_only_flg_spacer_ctrl, title_parts2_ctrl=self.camera_only_flg_ctrl, file_histories_key="camera_vmd", \
                                                          is_change_output=True, is_aster=False, is_save=False, set_no=1)
        self.header_sizer.Add(self.camera_vmd_file_ctrl.sizer, 1, wx.EXPAND, 0)

        # 出力先VMD파일コントロール
        self.output_camera_vmd_file_ctrl = BaseFilePickerCtrl(frame, self.header_panel, u"출력 카메라 VMD", u"출력 카메라 VMD 파일을 엽니다", ("vmd"), wx.FLP_OVERWRITE_PROMPT | wx.FLP_SAVE | wx.FLP_USE_TEXTCTRL, \
                                                              u"조정 결과의 카메라 VMD 출력 경로를 지정하십시오.\nVMD 파일명에 따라 자동 생성되지만 임의의 경로로 변경할 수도 있습니다.", \
                                                              is_aster=False, is_save=True, set_no=1)
        self.header_sizer.Add(self.output_camera_vmd_file_ctrl.sizer, 1, wx.EXPAND, 0)

        # 카메라距離調整スライダー
        self.camera_length_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.camera_length_txt = wx.StaticText(self.header_panel, wx.ID_ANY, u"거리 가동 범위", wx.DefaultPosition, wx.DefaultSize, 0)
        self.camera_length_txt.SetToolTip(u"스테이지의 크기보다, 카메라의 거리 조정 범위를 한정하고 싶은 경우에\n" \
                                          + "카메라의 거리 가동 범위를 한정할 수 있습니다.\n" \
                                          + "가동 범위는 수동으로 조정할 수도 있습니다.")
        self.camera_length_txt.Wrap(-1)
        self.camera_length_sizer.Add(self.camera_length_txt, 0, wx.ALL, 5)

        self.camera_length_type_ctrl = wx.Choice(self.header_panel, id=wx.ID_ANY, choices=["거리 제한 강", "거리 제한 약", "거리 제한 없음"])
        self.camera_length_type_ctrl.SetSelection(2)
        self.camera_length_type_ctrl.Bind(wx.EVT_CHOICE, self.on_camera_length_type)
        self.camera_length_type_ctrl.SetToolTip(u"'거리 제한 강'  …  작은 스테이지용. 거리 가동 범위를 엄격히 제한합니다.\n" \
                                                + "'거리 제한 약'  …  중간 스테이지용. 거리 가동 범위를 다소 제한합니다.\n" \
                                                + "'거리 제한 없음'  …  거리 가동 범위를 무제한으로 하여 원본 모델처럼 보이는 상태가 되도록 최대한 조정합니다")
        self.camera_length_sizer.Add(self.camera_length_type_ctrl, 0, wx.ALL, 5)

        self.camera_length_label = wx.StaticText(self.header_panel, wx.ID_ANY, u"（5）", wx.DefaultPosition, wx.DefaultSize, 0)
        self.camera_length_label.SetToolTip(u"현재 지정된 카메라 거리의 가동범위입니다.")
        self.camera_length_label.Wrap(-1)
        self.camera_length_sizer.Add(self.camera_length_label, 0, wx.ALL, 5)

        self.camera_length_slider = FloatSliderCtrl(self.header_panel, wx.ID_ANY, 5, 1, 5, 0.01, self.camera_length_label, wx.DefaultPosition, wx.DefaultSize, wx.SL_HORIZONTAL)
        self.camera_length_slider.Bind(wx.EVT_SCROLL_CHANGED, self.set_output_vmd_path)
        self.camera_length_sizer.Add(self.camera_length_slider, 1, wx.ALL | wx.EXPAND, 5)

        self.header_sizer.Add(self.camera_length_sizer, 0, wx.ALL | wx.EXPAND, 5)

        self.header_panel.SetSizer(self.header_sizer)
        self.header_panel.Layout()
        self.sizer.Add(self.header_panel, 0, wx.EXPAND | wx.ALL, 5)

        # 카메라セット(key: 파일セット番号, value: 카메라セット)
        self.camera_set_dict = {}
        # Bulk用카메라セット
        self.bulk_camera_set_dict = {}
        # 카메라セット用基本Sizer
        self.set_list_sizer = wx.BoxSizer(wx.VERTICAL)

        self.scrolled_window = CameraScrolledWindow(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, \
                                                    wx.FULL_REPAINT_ON_RESIZE | wx.VSCROLL | wx.ALWAYS_SHOW_SB)
        self.scrolled_window.SetScrollRate(5, 5)

        # スクロールバーの表示のためにサイズ調整
        self.scrolled_window.SetSizer(self.set_list_sizer)
        self.scrolled_window.Layout()
        self.sizer.Add(self.scrolled_window, 1, wx.ALL | wx.EXPAND | wx.FIXED_MINSIZE, 5)
        self.sizer.Layout()
        self.fit()

    def on_camera_length_type(self, event):
        if self.camera_length_type_ctrl.GetSelection() == 0:
            self.camera_length_slider.SetValue(1.05)
        elif self.camera_length_type_ctrl.GetSelection() == 1:
            self.camera_length_slider.SetValue(1.3)
        else:
            self.camera_length_slider.SetValue(5)

        self.set_output_vmd_path(event)

    def set_output_vmd_path(self, event, is_force=False):
        # 카메라出力パスを強制的に変更する
        self.header_panel.set_output_vmd_path(event, True)

    # 카메라タブ初期化処理
    def initialize(self, event: wx.Event):
        self.bulk_camera_set_dict = {}

        if 1 not in self.camera_set_dict:
            # 空から作る場合、파일タブの파일セット参照
            self.add_set(1, self.frame.file_panel_ctrl.file_set)
        else:
            # ある場合、모델名だけ入替
            self.camera_set_dict[1].model_name_txt.SetLabel("{0} → {1}".format(\
                                                            self.frame.file_panel_ctrl.file_set.org_model_file_ctrl.file_model_ctrl.txt_ctrl.GetValue()[1:-1], \
                                                            self.frame.file_panel_ctrl.file_set.rep_model_file_ctrl.file_model_ctrl.txt_ctrl.GetValue()[1:-1]))

        # multiはあるだけ調べる
        for multi_file_set_idx, multi_file_set in enumerate(self.frame.multi_panel_ctrl.file_set_list):
            set_no = multi_file_set_idx + 2
            if set_no not in self.camera_set_dict:
                # 空から作る場合、複数タブの파일セット参照
                self.add_set(set_no, multi_file_set)
            else:
                # ある場合、모델名だけ入替
                self.camera_set_dict[set_no].model_name_txt.SetLabel("{0} → {1}".format(\
                                                                     multi_file_set.org_model_file_ctrl.file_model_ctrl.txt_ctrl.GetValue()[1:-1], \
                                                                     multi_file_set.rep_model_file_ctrl.file_model_ctrl.txt_ctrl.GetValue()[1:-1]))

    def add_set(self, set_idx: int, file_set: SizingFileSet):
        new_camera_set = CameraSet(self.frame, self, self.scrolled_window, set_idx, file_set)
        self.set_list_sizer.Add(new_camera_set.set_sizer, 0, wx.EXPAND | wx.ALL, 5)
        self.camera_set_dict[set_idx] = new_camera_set

        # スクロールバーの表示のためにサイズ調整
        self.set_list_sizer.Layout()
        self.set_list_sizer.FitInside(self.scrolled_window)

    # フォーム無効化
    def disable(self):
        self.file_set.disable()

    # フォーム無効化
    def enable(self):
        self.file_set.enable()

    def save(self):
        self.camera_vmd_file_ctrl.save()


class CameraScrolledWindow(wx.ScrolledWindow):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

    # 複数모션用카메라の場合、出力パスは変わらないのでスルー
    def set_output_vmd_path(self, event: wx.Event, is_force=False):
        pass


class CameraHeaderPanel(wx.Panel):

    def __init__(self, frame, parent, id=wx.ID_ANY, pos=wx.DefaultPosition, size=wx.DefaultSize, style=wx.TAB_TRAVERSAL, name=wx.PanelNameStr):
        super().__init__(parent, id=id, pos=pos, size=size, style=style, name=name)

        self.parent = parent
        self.frame = frame

    # 파일変更時の処理
    def on_change_file(self, event: wx.Event):
        self.set_output_vmd_path(event)

    def set_output_vmd_path(self, event, is_force=False):
        output_camera_vmd_path = MFileUtils.get_output_camera_vmd_path(
            self.parent.camera_vmd_file_ctrl.file_ctrl.GetPath(),
            self.frame.file_panel_ctrl.file_set.rep_model_file_ctrl.file_ctrl.GetPath(),
            self.parent.output_camera_vmd_file_ctrl.file_ctrl.GetPath(),
            self.parent.camera_length_slider.GetValue(), is_force)

        self.parent.output_camera_vmd_file_ctrl.file_ctrl.SetPath(output_camera_vmd_path)

        if len(output_camera_vmd_path) >= 255 and os.name == "nt":
            logger.error("생성 예정인 파일 경로가 Windows 제한을 초과했습니다.\n 생성 예정 경로: {0}".format(output_camera_vmd_path), decoration=MLogger.DECORATION_BOX)


class CameraSet():

    def __init__(self, frame: wx.Frame, panel: wx.Panel, window: wx.Window, set_idx: int, file_set: SizingFileSet):
        self.frame = frame
        self.panel = panel
        self.window = window
        self.set_idx = set_idx
        self.file_set = file_set

        self.set_sizer = wx.StaticBoxSizer(wx.StaticBox(self.window, wx.ID_ANY, "【No.{0}】".format(set_idx)), orient=wx.VERTICAL)

        self.model_name_txt = wx.StaticText(self.window, wx.ID_ANY, \
                                            "{0} → {1}".format(file_set.org_model_file_ctrl.file_model_ctrl.txt_ctrl.GetValue()[1:-1], \
                                                               file_set.rep_model_file_ctrl.file_model_ctrl.txt_ctrl.GetValue()[1:-1]), wx.DefaultPosition, wx.DefaultSize, 0)
        self.model_name_txt.Wrap(-1)
        self.set_sizer.Add(self.model_name_txt, 0, wx.ALL, 5)

        # 카메라PMX파일コントロール
        self.camera_model_file_ctrl = HistoryFilePickerCtrl(frame, window, u"카메라 작성 원본 모델 PMX", u"카메라 작성 원본 모델 PMX 파일을 엽니다", ("pmx"), wx.FLP_DEFAULT_STYLE, \
                                                            u"카메라 작성에 사용된 원본 모델의 PMX 경로를 지정하십시오.\n미지정시 모션 작성 원본 모델 PMX를 사용합니다." \
                                                            + "\n정밀도는 떨어지지만, 유사한 사이즈, 본 구조의 모델로도 대용할 수 있습니다.\nD&D에서의 지정, 열기 버튼에서의 지정, 이력에서의 선택이 가능합니다.", \
                                                            file_model_spacer=20, title_parts_ctrl=None, title_parts2_ctrl=None, file_histories_key="camera_pmx", \
                                                            is_change_output=True, is_aster=False, is_save=False, set_no=set_idx)
        self.set_sizer.Add(self.camera_model_file_ctrl.sizer, 1, wx.EXPAND, 0)

        self.offset_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.camera_offset_y_txt = wx.StaticText(self.window, wx.ID_ANY, u"전체 길이 Y 오프셋", wx.DefaultPosition, wx.DefaultSize, 0)
        self.camera_offset_y_txt.Wrap(-1)
        self.offset_sizer.Add(self.camera_offset_y_txt, 0, wx.ALL, 5)

        # 오프셋Yコントロール
        self.camera_offset_y_ctrl = wx.SpinCtrlDouble(self.window, id=wx.ID_ANY, size=wx.Size(100, -1), value="0.0", min=-1000, max=1000, initial=0.0, inc=0.1)
        self.camera_offset_y_ctrl.SetToolTip(u"카메라에 비추는 변환용 모델의 전체 길이를 조정하는 오프셋 값을 지정할 수 있습니다.\n" \
                                             + "머리 장식 등 머리보다 위에 있는 오브젝트를 제외하고자 하는 경우 마이너스 값을 지정하십시오.\n" \
                                             + "바보털 등 머리보다 위에 있는 오브젝트를 포함하고 싶은' 경우 플러스 값을 지정하십시오.")
        self.camera_offset_y_ctrl.Bind(wx.EVT_MOUSEWHEEL, lambda event: self.frame.on_wheel_spin_ctrl(event, 0.2))
        self.offset_sizer.Add(self.camera_offset_y_ctrl, 0, wx.ALL, 5)

        self.set_sizer.Add(self.offset_sizer, 0, wx.ALL, 0)


