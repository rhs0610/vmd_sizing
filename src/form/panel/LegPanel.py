# -*- coding: utf-8 -*-
#
import wx
import wx.lib.newevent
import numpy as np

from form.panel.BasePanel import BasePanel
from form.parts.FloatSliderCtrl import FloatSliderCtrl
from form.parts.SizingFileSet import SizingFileSet
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)


class LegPanel(BasePanel):

    def __init__(self, frame: wx.Frame, parent: wx.Notebook, tab_idx: int):
        super().__init__(frame, parent, tab_idx)

        # 전체이동量보정 --------------------

        move_correction_tooltip = "센터·발 IK등의 이동계열 본의 전체 이동량을 보정할 수 있습니다.\n복수인원 모션의 포메이션을 전체적으로 펼치고 싶거나, 조금 움직임을 다이나믹하게 하고 싶을 때 사용하세요."
        self.move_correction_title_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 전체이동量보정タイトル
        self.move_correction_title_txt = wx.StaticText(self, wx.ID_ANY, u"전체 이동량 보정", wx.DefaultPosition, wx.DefaultSize, 0)
        self.move_correction_title_txt.SetToolTip(move_correction_tooltip)
        self.move_correction_title_txt.Wrap(-1)
        self.move_correction_title_txt.SetFont(wx.Font(wx.NORMAL_FONT.GetPointSize(), wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False, wx.EmptyString))
        self.move_correction_title_sizer.Add(self.move_correction_title_txt, 0, wx.ALL, 5)
        self.sizer.Add(self.move_correction_title_sizer, 0, wx.ALL, 5)

        # 전체이동量보정説明文
        self.move_correction_description_txt = wx.StaticText(self, wx.ID_ANY, move_correction_tooltip, wx.DefaultPosition, wx.DefaultSize, 0)
        self.sizer.Add(self.move_correction_description_txt, 0, wx.ALL, 5)

        # 전체이동量보정スライダー
        self.move_correction_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.move_correction_txt = wx.StaticText(self, wx.ID_ANY, u"전체 이동량 보정값", wx.DefaultPosition, wx.DefaultSize, 0)
        self.move_correction_txt.SetToolTip(u"키 비율에 곱하는 보정치입니다. 기본적으로는 1명일 경우 1, 복수명일 경우 머리·몸 비율을 설정하고 있습니다.")
        self.move_correction_txt.Wrap(-1)
        self.move_correction_sizer.Add(self.move_correction_txt, 0, wx.ALL, 5)

        self.move_correction_label = wx.StaticText(self, wx.ID_ANY, u"（1）", wx.DefaultPosition, wx.DefaultSize, 0)
        self.move_correction_label.SetToolTip(u"현재 지정되어 있는 전체 이동량 보정값입니다.")
        self.move_correction_label.Wrap(-1)
        self.move_correction_sizer.Add(self.move_correction_label, 0, wx.ALL, 5)

        self.move_correction_slider = FloatSliderCtrl(self, wx.ID_ANY, 1, 0.5, 1.5, 0.05, self.move_correction_label, wx.DefaultPosition, wx.DefaultSize, wx.SL_HORIZONTAL)
        self.move_correction_slider.Bind(wx.EVT_SCROLL_CHANGED, self.on_check_move_correction)
        self.move_correction_sizer.Add(self.move_correction_slider, 1, wx.ALL | wx.EXPAND, 5)

        self.sizer.Add(self.move_correction_sizer, 0, wx.ALL | wx.EXPAND, 5)

        self.static_line01 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.sizer.Add(self.static_line01, 0, wx.EXPAND | wx.ALL, 5)

        # 오프셋値
        self.leg_offset_set_dict = {}
        # 오프셋用ダイアログ
        self.leg_offset_dialog = LegOffsetDialog(self.frame)

        # 발 IK오프셋 --------------------

        # Bulk用발 IK오프셋データ
        self.bulk_leg_offset_set_dict = {}

        leg_offset_tooltip = "발 IK의 이동량 오프셋을 설정할 수 있습니다.\n다리를 닫았을 때 겹쳐버리거나 전체의 이동량은 바꾸지 않고 개별 발IK의 이동량만큼 조정하고 싶을 때 사용하시면 됩니다."

        # 발 IK오프셋 ----------------
        self.leg_offset_title_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 발 IK오프셋タイトル
        self.leg_offset_title_txt = wx.StaticText(self, wx.ID_ANY, u"발 IK 오프셋", wx.DefaultPosition, wx.DefaultSize, 0)
        self.leg_offset_title_txt.SetToolTip(leg_offset_tooltip)
        self.leg_offset_title_txt.Wrap(-1)
        self.leg_offset_title_txt.SetFont(wx.Font(wx.NORMAL_FONT.GetPointSize(), wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False, wx.EmptyString))
        self.leg_offset_title_sizer.Add(self.leg_offset_title_txt, 0, wx.ALL, 5)
        self.sizer.Add(self.leg_offset_title_sizer, 0, wx.ALL, 5)

        # 발 IK오프셋説明文
        self.leg_offset_description_txt = wx.StaticText(self, wx.ID_ANY, leg_offset_tooltip, wx.DefaultPosition, wx.DefaultSize, 0)
        self.sizer.Add(self.leg_offset_description_txt, 0, wx.ALL, 5)

        self.leg_offset_target_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 오프셋値지정
        self.leg_offset_target_txt_ctrl = wx.TextCtrl(self, wx.ID_ANY, "", wx.DefaultPosition, (450, 80), wx.HSCROLL | wx.VSCROLL | wx.TE_MULTILINE | wx.TE_READONLY)
        self.leg_offset_target_txt_ctrl.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DLIGHT))
        self.leg_offset_target_sizer.Add(self.leg_offset_target_txt_ctrl, 1, wx.EXPAND | wx.ALL, 5)

        self.leg_offset_target_btn_ctrl = wx.Button(self, wx.ID_ANY, u"오프셋 지정", wx.DefaultPosition, wx.DefaultSize, 0)
        self.leg_offset_target_btn_ctrl.SetToolTip(u"변환용 모델의 발 IK오프셋값을 지정할 수 있습니다.")
        self.leg_offset_target_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_click_leg_offset_target)
        self.leg_offset_target_sizer.Add(self.leg_offset_target_btn_ctrl, 0, wx.ALIGN_BOTTOM | wx.ALL, 5)

        self.sizer.Add(self.leg_offset_target_sizer, 0, wx.ALL, 0)

        self.static_line03 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.sizer.Add(self.static_line03, 0, wx.EXPAND | wx.ALL, 5)

        self.fit()

    def get_leg_offsets(self):
        if len(self.bulk_leg_offset_set_dict.keys()) > 0:
            # Bulk用データがある場合, 優先返還
            return self.bulk_leg_offset_set_dict

        target = {}

        # 選択された오프셋値を入力欄に설정(ハッシュが同じ場合のみ)
        if 1 in self.leg_offset_set_dict and self.leg_offset_set_dict[1].leg_offset_slider:
            if self.leg_offset_set_dict[1].equal_hashdigest(self.frame.file_panel_ctrl.file_set):
                target[0] = self.leg_offset_set_dict[1].leg_offset_slider.GetValue()
            else:
                logger.warning("【No.%s】발 IK 오프셋 설정 후, 파일 세트이 변경되었기 때문에 발 IK 오프셋을 클리어합니다.", 1, decoration=MLogger.DECORATION_BOX)

        for set_no in list(self.leg_offset_set_dict.keys())[1:]:
            if set_no in self.leg_offset_set_dict and self.leg_offset_set_dict[set_no].leg_offset_slider:
                if len(self.frame.multi_panel_ctrl.file_set_list) >= set_no - 1 and self.leg_offset_set_dict[set_no].equal_hashdigest(self.frame.multi_panel_ctrl.file_set_list[set_no - 2]):
                    target[set_no - 1] = self.leg_offset_set_dict[set_no].leg_offset_slider.GetValue()
                else:
                    logger.warning("【No.%s】발 IK 오프셋 설정 후, 파일 세트이 변경되었기 때문에 발 IK 오프셋을 클리어합니다.", set_no, decoration=MLogger.DECORATION_BOX)

        return target

    def on_click_leg_offset_target(self, event: wx.Event):
        if self.leg_offset_dialog.ShowModal() == wx.ID_CANCEL:
            return     # the user changed their mind

        self.show_leg_offset()

        self.leg_offset_dialog.Hide()

    def show_leg_offset(self):
        # 一旦クリア
        self.leg_offset_target_txt_ctrl.SetValue("")

        # 選択された오프셋値を入力欄に설정
        texts = []
        for set_no, set_data in self.leg_offset_set_dict.items():
            # 選択肢ごとの表示文言
            texts.append("【No.{0}】　{1}".format(set_no, set_data.leg_offset_slider.GetValue()))

        self.leg_offset_target_txt_ctrl.WriteText(" / ".join(texts))

    def initialize(self, event: wx.Event):

        if 1 in self.leg_offset_set_dict:
            # 파일タブ用발 IK오프셋の파일세트がある場合
            if self.frame.file_panel_ctrl.file_set.is_loaded():
                # 既にある場合, ハッシュチェック
                if self.leg_offset_set_dict[1].equal_hashdigest(self.frame.file_panel_ctrl.file_set):
                    # 同じである場合, スルー
                    pass
                else:
                    # 違う場合, 파일세트読み直し
                    self.add_set(1, self.frame.file_panel_ctrl.file_set, replace=True)
            else:
                # 파일タブが読み込み失敗している場合, 読み直し（クリア）
                self.add_set(1, self.frame.file_panel_ctrl.file_set, replace=True)
        else:
            # 空から作る場合, 파일タブの파일세트参照
            self.add_set(1, self.frame.file_panel_ctrl.file_set, replace=False)

        # multiはあるだけ調べる
        for multi_file_set_idx, multi_file_set in enumerate(self.frame.multi_panel_ctrl.file_set_list):
            set_no = multi_file_set_idx + 2
            if set_no in self.leg_offset_set_dict:
                # 複数タブ用발 IK오프셋の파일세트がある場合
                if multi_file_set.is_loaded():
                    # 既にある場合, ハッシュチェック
                    if self.leg_offset_set_dict[set_no].equal_hashdigest(multi_file_set):
                        # 同じである場合, スルー
                        pass
                    else:
                        # 違う場合, 파일세트読み直し
                        self.add_set(set_no, multi_file_set, replace=True)
                else:
                    # 複数タブが読み込み失敗している場合, 読み直し（クリア）
                    self.add_set(set_no, multi_file_set, replace=True)
            else:
                # 空から作る場合, 複数タブの파일세트参照
                self.add_set(set_no, multi_file_set, replace=False)

        self.show_leg_offset()

        event.Skip()

    # VMD出力파일パス生成
    def set_output_vmd_path(self, event, is_force=False):
        # 念のため出力파일パス自動生成（空の場合설정）
        self.frame.file_panel_ctrl.file_set.set_output_vmd_path(event)

        # multiのも出力파일パス自動生成（空の場合설정）
        for file_set in self.frame.multi_panel_ctrl.file_set_list:
            file_set.set_output_vmd_path(event)

    def on_check_move_correction(self, event: wx.Event):
        # パス再生成
        self.set_output_vmd_path(event)

        event.Skip()

    def add_set(self, set_idx: int, file_set: SizingFileSet, replace: bool):
        new_leg_offset_set = LegOffsetSet(self.frame, self, self.leg_offset_dialog.scrolled_window, set_idx, file_set)
        if replace:
            # 置き換え
            self.leg_offset_dialog.set_list_sizer.Hide(self.leg_offset_set_dict[set_idx].set_sizer, recursive=True)
            self.leg_offset_dialog.set_list_sizer.Replace(self.leg_offset_set_dict[set_idx].set_sizer, new_leg_offset_set.set_sizer, recursive=True)

            # 置き換えの場合, 오프셋値クリア
            self.leg_offset_target_txt_ctrl.SetValue("")
        else:
            # 新規追加
            self.leg_offset_dialog.set_list_sizer.Add(new_leg_offset_set.set_sizer, 0, wx.EXPAND | wx.ALL, 5)
        self.leg_offset_set_dict[set_idx] = new_leg_offset_set

        # スクロールバーの表示のためにサイズ調整
        self.leg_offset_dialog.set_list_sizer.Layout()
        self.leg_offset_dialog.set_list_sizer.FitInside(self.leg_offset_dialog.scrolled_window)


class LegOffsetSet():

    def __init__(self, frame: wx.Frame, panel: wx.Panel, window: wx.Window, set_idx: int, file_set: SizingFileSet):
        self.frame = frame
        self.panel = panel
        self.window = window
        self.set_idx = set_idx
        self.file_set = file_set
        self.rep_model_digest = 0 if not file_set.rep_model_file_ctrl.data else file_set.rep_model_file_ctrl.data.digest

        self.set_sizer = wx.StaticBoxSizer(wx.StaticBox(self.window, wx.ID_ANY, "【No.{0}】 {1}".format(set_idx, file_set.rep_model_file_ctrl.data.name[:20])), orient=wx.VERTICAL)

        # 발 IK오프셋値
        self.leg_offset_label = wx.StaticText(self.window, wx.ID_ANY, "（0）", wx.DefaultPosition, wx.DefaultSize, 0)
        self.leg_offset_label.SetToolTip(u"현재 지정된 발 IK 오프셋 값입니다. 실제로 이 값이 (방향을 가미하여) 발IK에 가산됩니다.")
        self.leg_offset_label.Wrap(-1)
        self.set_sizer.Add(self.leg_offset_label, 0, wx.ALL, 5)

        self.leg_offset_slider = FloatSliderCtrl(self.window, wx.ID_ANY, 0, -2, 2, 0.05, self.leg_offset_label, wx.DefaultPosition, wx.DefaultSize, wx.SL_HORIZONTAL)
        self.set_sizer.Add(self.leg_offset_slider, 1, wx.ALL | wx.EXPAND, 5)

    # 現在の파일세트のハッシュと同じであるかチェック
    def equal_hashdigest(self, now_file_set: SizingFileSet):
        return self.rep_model_digest == now_file_set.rep_model_file_ctrl.data.digest


class LegOffsetDialog(wx.Dialog):

    def __init__(self, parent):
        super().__init__(parent, id=wx.ID_ANY, title="발 IK 오프셋 지정", pos=(-1, -1), size=(800, 500), style=wx.DEFAULT_DIALOG_STYLE, name="LegOffsetDialog")

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        # 説明文
        self.description_txt = wx.StaticText(self, wx.ID_ANY, u"발 IK의 이동량 오프셋을 설정할 수 있습니다. 실제로 이 값이 (방향을 가미하여) 발IK에 가산됩니다.\n" \
                                             + u"복수 인원 모션의 경우, 너무 큰 오프셋을 지정하면 포메이션이 무너지는 경우가 있습니다.\n" , wx.DefaultPosition, wx.DefaultSize, 0)
        self.sizer.Add(self.description_txt, 0, wx.ALL, 5)

        # ボタン
        self.btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.ok_btn = wx.Button(self, wx.ID_OK, "OK")
        self.btn_sizer.Add(self.ok_btn, 0, wx.ALL, 5)

        self.calcel_btn = wx.Button(self, wx.ID_CANCEL, "취소")
        self.btn_sizer.Add(self.calcel_btn, 0, wx.ALL, 5)
        self.sizer.Add(self.btn_sizer, 0, wx.ALL, 5)

        self.static_line01 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.sizer.Add(self.static_line01, 0, wx.EXPAND | wx.ALL, 5)

        self.scrolled_window = wx.ScrolledWindow(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, \
                                                 wx.FULL_REPAINT_ON_RESIZE | wx.VSCROLL | wx.ALWAYS_SHOW_SB)
        self.scrolled_window.SetScrollRate(5, 5)

        # 발 IK오프셋세트用基本Sizer
        self.set_list_sizer = wx.BoxSizer(wx.VERTICAL)

        # スクロールバーの表示のためにサイズ調整
        self.scrolled_window.SetSizer(self.set_list_sizer)
        self.scrolled_window.Layout()
        self.sizer.Add(self.scrolled_window, 1, wx.ALL | wx.EXPAND, 5)
        self.SetSizer(self.sizer)
        self.sizer.Layout()

        # 画面中央に表示
        self.CentreOnScreen()

        # 最初は隠しておく
        self.Hide()
