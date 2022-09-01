# -*- coding: utf-8 -*-
#
import wx
import wx.lib.newevent
import numpy as np

from form.panel.BasePanel import BasePanel
from form.parts.FloatSliderCtrl import FloatSliderCtrl
from form.parts.SizingFileSet import SizingFileSet
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)


class ArmPanel(BasePanel):

    def __init__(self, frame: wx.Frame, parent: wx.Notebook, tab_idx: int):
        super().__init__(frame, parent, tab_idx)

        # rigid body list
        self.avoidance_set_dict = {}
        # Dialog for rigid body
        self.avoidance_dialog = AvoidanceDialog(self.frame)

        avoidance_tooltip = "지정 문자열명의 본 추종 강체와 손목, 손가락과의 접촉을 회피합니다.\n선택 버튼에서 변환용 모델의 회피시키고 싶은 본 추종 강체를 선택하십시오.\n" \
                            + "'머리 접촉 회피'는 머리를 중심으로 한 구체 강체를 자동으로 계산합니다."
        alignment_tooltip = "변환용 모델의 손목 위치가 원본 모델의 손목과 거의 같은 위치가 되도록 손목 위치를 조정합니다."

        # Contact avoidance data for bulk
        self.bulk_avoidance_set_dict = {}

        self.description_txt = wx.StaticText(self, wx.ID_ANY, "팔을 변환용 모델에 맞게 조정할 수 있습니다.\n '접촉 회피'와 '위치 맞추기'를 함께 실행할 수 있습니다.(접촉 회피 → 위치 맞춤 순으로 실행)" + \
                                             "\n팔의 움직임이 원래 모션에서 바뀔 수 있습니다.모두 나름대로 시간이 걸립니다.", wx.DefaultPosition, wx.DefaultSize, 0)
        self.sizer.Add(self.description_txt, 0, wx.ALL, 5)

        self.static_line01 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.sizer.Add(self.static_line01, 0, wx.EXPAND | wx.ALL, 5)

        # rigid body contact aviod ----------------
        self.avoidance_title_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # rigid body contact aviod title
        self.avoidance_title_txt = wx.StaticText(self, wx.ID_ANY, u"접촉 회피", wx.DefaultPosition, wx.DefaultSize, 0)
        self.avoidance_title_txt.SetToolTip(avoidance_tooltip)
        self.avoidance_title_txt.Wrap(-1)
        self.avoidance_title_txt.SetFont(wx.Font(wx.NORMAL_FONT.GetPointSize(), wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False, wx.EmptyString))
        self.avoidance_title_txt.Bind(wx.EVT_LEFT_DOWN, self.on_check_arm_process_avoidance)

        self.arm_process_flg_avoidance = wx.CheckBox(self, wx.ID_ANY, u"", wx.DefaultPosition, wx.DefaultSize)
        self.arm_process_flg_avoidance.SetToolTip(avoidance_tooltip)
        self.arm_process_flg_avoidance.Bind(wx.EVT_CHECKBOX, self.set_output_vmd_path)
        self.avoidance_title_sizer.Add(self.arm_process_flg_avoidance, 0, wx.ALL, 5)
        self.avoidance_title_sizer.Add(self.avoidance_title_txt, 0, wx.ALL, 5)
        self.sizer.Add(self.avoidance_title_sizer, 0, wx.ALL, 5)

        # rigid body contact aviod instruction
        self.avoidance_description_txt = wx.StaticText(self, wx.ID_ANY, avoidance_tooltip, wx.DefaultPosition, wx.DefaultSize, 0)
        self.sizer.Add(self.avoidance_description_txt, 0, wx.ALL, 5)

        self.avoidance_target_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # rigid body name definition
        self.avoidance_target_txt_ctrl = wx.TextCtrl(self, wx.ID_ANY, "", wx.DefaultPosition, (450, 80), wx.HSCROLL | wx.VSCROLL | wx.TE_MULTILINE | wx.TE_READONLY)
        self.avoidance_target_txt_ctrl.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DLIGHT))
        self.avoidance_target_txt_ctrl.Bind(wx.EVT_TEXT, self.on_check_arm_process_avoidance)
        self.avoidance_target_sizer.Add(self.avoidance_target_txt_ctrl, 1, wx.EXPAND | wx.ALL, 5)

        self.avoidance_target_btn_ctrl = wx.Button(self, wx.ID_ANY, u"강체 선택", wx.DefaultPosition, wx.DefaultSize, 0)
        self.avoidance_target_btn_ctrl.SetToolTip(u"변환용 모델에 있는 본 추종 강체를 선택할 수 있습니다.")
        self.avoidance_target_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_click_avoidance_target)
        self.avoidance_target_sizer.Add(self.avoidance_target_btn_ctrl, 0, wx.ALIGN_BOTTOM | wx.ALL, 5)

        self.sizer.Add(self.avoidance_target_sizer, 0, wx.ALL, 0)

        self.static_line03 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.sizer.Add(self.static_line03, 0, wx.EXPAND | wx.ALL, 5)

        # Hand position adjustment --------------------
        self.alignment_title_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Hand position adjustment title
        self.alignment_title_txt = wx.StaticText(self, wx.ID_ANY, u"위치 맞춤", wx.DefaultPosition, wx.DefaultSize, 0)
        self.alignment_title_txt.SetToolTip("양손을 모으거나 바닥에 손을 짚는 모션을 변환용 모델의 손목 위치에 맞게 조정합니다.\n" + \
                                            "각각의 거리를 조정함으로써 위치 맞춤 적용 범위를 조정할 수 있습니다.")
        self.alignment_title_txt.Wrap(-1)
        self.alignment_title_txt.SetFont(wx.Font(wx.NORMAL_FONT.GetPointSize(), wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False, wx.EmptyString))
        self.alignment_title_txt.Bind(wx.EVT_LEFT_DOWN, self.on_check_arm_process_alignment)

        self.arm_process_flg_alignment = wx.CheckBox(self, wx.ID_ANY, u"", wx.DefaultPosition, wx.DefaultSize)
        self.arm_process_flg_alignment.SetToolTip(alignment_tooltip)
        self.arm_process_flg_alignment.Bind(wx.EVT_CHECKBOX, self.set_output_vmd_path)
        self.alignment_title_sizer.Add(self.arm_process_flg_alignment, 0, wx.ALL, 5)
        self.alignment_title_sizer.Add(self.alignment_title_txt, 0, wx.ALL, 5)
        self.sizer.Add(self.alignment_title_sizer, 0, wx.ALL, 5)

        # Hand position adjustment instruction
        self.alignment_description_txt = wx.StaticText(self, wx.ID_ANY, alignment_tooltip, wx.DefaultPosition, wx.DefaultSize, 0)
        self.sizer.Add(self.alignment_description_txt, 0, wx.ALL, 5)

        # Option sizer
        self.alignment_option_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Finger position adjustment
        self.arm_alignment_finger_flg_ctrl = wx.CheckBox(self, wx.ID_ANY, u"손가락 위치에서 위치 맞춤을 합니다.", wx.DefaultPosition, wx.DefaultSize, 0)
        self.arm_alignment_finger_flg_ctrl.SetToolTip(u"체크를 하면 핑거 탭 모션 등 손가락 사이의 거리를 기준으로 손목 위치를 조정할 수 있습니다." \
                                                      + "복수 인원 모션에서는 OFF인 채로 있는 것이 깨끗해집니다.")
        self.arm_alignment_finger_flg_ctrl.Bind(wx.EVT_CHECKBOX, self.on_check_arm_process_alignment)
        self.alignment_option_sizer.Add(self.arm_alignment_finger_flg_ctrl, 0, wx.ALL, 5)

        # Floor position adjustment
        self.arm_alignment_floor_flg_ctrl = wx.CheckBox(self, wx.ID_ANY, u"바닥과의 위치 맞춤도 함께 합니다.", wx.DefaultPosition, wx.DefaultSize, 0)
        self.arm_alignment_floor_flg_ctrl.SetToolTip(u"체크를 하면 손목이 바닥에 가라앉거나 뜨는 경우에 원래 모델에 맞게 손목의 위치를 조절할 수 있습니다.\n센터 위치도 함께 조정합니다.")
        self.arm_alignment_floor_flg_ctrl.Bind(wx.EVT_CHECKBOX, self.on_check_arm_process_alignment)
        self.alignment_option_sizer.Add(self.arm_alignment_floor_flg_ctrl, 0, wx.ALL, 5)

        self.sizer.Add(self.alignment_option_sizer, 0, wx.ALL, 5)

        # Wrist position slider
        self.alignment_distance_wrist_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.alignment_distance_wrist_txt = wx.StaticText(self, wx.ID_ANY, u"손목 사이의 거리　  ", wx.DefaultPosition, wx.DefaultSize, 0)
        self.alignment_distance_wrist_txt.SetToolTip(u"어느 정도 손목이 가까워졌을 경우 손목 위치 맞춤을 실행할지 지정하십시오.\n값이 작을수록 손목이 가까워졌을 때만 손목 위치 맞춤을 합니다.\n거리의 단위는 원 모델의 손바닥 크기입니다." \
                                                     + "\n사이징 실행 시 손목 간의 거리가 메시지란에 나와 있으니 참고해 주세요.\n슬라이더를 최대로 설정하면 항상 손목 위치 맞춤을 진행합니다.(양손 검 등에 편리합니다)")
        self.alignment_distance_wrist_txt.Wrap(-1)
        self.alignment_distance_wrist_sizer.Add(self.alignment_distance_wrist_txt, 0, wx.ALL, 5)

        self.alignment_distance_wrist_label = wx.StaticText(self, wx.ID_ANY, u"（1.7）", wx.DefaultPosition, wx.DefaultSize, 0)
        self.alignment_distance_wrist_label.SetToolTip(u"현재 지정된 손목 사이의 거리입니다.원 모델의 양쪽 손목 위치가 이 범위 내일 경우 손목 간의 위치 맞춤을 실시합니다.")
        self.alignment_distance_wrist_label.Wrap(-1)
        self.alignment_distance_wrist_sizer.Add(self.alignment_distance_wrist_label, 0, wx.ALL, 5)

        self.alignment_distance_wrist_slider = FloatSliderCtrl(self, wx.ID_ANY, 1.7, 0, 10, 0.1, self.alignment_distance_wrist_label, wx.DefaultPosition, wx.DefaultSize, wx.SL_HORIZONTAL)
        self.alignment_distance_wrist_slider.Bind(wx.EVT_SCROLL_CHANGED, self.on_check_arm_process_alignment)
        self.alignment_distance_wrist_sizer.Add(self.alignment_distance_wrist_slider, 1, wx.ALL | wx.EXPAND, 5)

        self.sizer.Add(self.alignment_distance_wrist_sizer, 0, wx.ALL | wx.EXPAND, 5)

        # Finger position slider
        self.alignment_distance_finger_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.alignment_distance_finger_txt = wx.StaticText(self, wx.ID_ANY, u"손가락 사이의 거리　　  ", wx.DefaultPosition, wx.DefaultSize, 0)
        self.alignment_distance_finger_txt.SetToolTip(u"어느 정도 손가락이 가까워졌을 경우 손가락 위치 맞춤을 실행할지 지정하십시오.\n값이 작을수록 손가락이 가까워졌을 때만 손가락 위치 맞춤을 합니다.\n거리의 단위는 원 모델의 손바닥 크기입니다.\n" \
                                                      + "\n사이징 실행 시 손가락 사이의 거리가 메시지란에 나와 있으니 참고하시기 바랍니다.\n슬라이더를 최대로 설정하면 항상 손가락 위치 맞춤을 합니다.")
        self.alignment_distance_finger_txt.Wrap(-1)
        self.alignment_distance_finger_sizer.Add(self.alignment_distance_finger_txt, 0, wx.ALL, 5)

        self.alignment_distance_finger_label = wx.StaticText(self, wx.ID_ANY, u"（1.4）", wx.DefaultPosition, wx.DefaultSize, 0)
        self.alignment_distance_finger_label.SetToolTip(u"현재 지정된 손가락 사이의 거리입니다.원모델의 두 손가락 위치가 이 범위 내인 경우, 손가락 사이의 위치맞춤을 실시합니다.")
        self.alignment_distance_finger_label.Wrap(-1)
        self.alignment_distance_finger_sizer.Add(self.alignment_distance_finger_label, 0, wx.ALL, 5)

        self.alignment_distance_finger_slider = FloatSliderCtrl(self, wx.ID_ANY, 1.4, 0, 10, 0.1, self.alignment_distance_finger_label, wx.DefaultPosition, wx.DefaultSize, wx.SL_HORIZONTAL)
        self.alignment_distance_finger_slider.Bind(wx.EVT_SCROLL_CHANGED, self.on_check_arm_process_alignment)
        self.alignment_distance_finger_sizer.Add(self.alignment_distance_finger_slider, 1, wx.ALL | wx.EXPAND, 5)

        self.sizer.Add(self.alignment_distance_finger_sizer, 0, wx.ALL | wx.EXPAND, 5)

        # Slider for wrist and flood
        self.alignment_distance_floor_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.alignment_distance_floor_txt = wx.StaticText(self, wx.ID_ANY, u"손목과 바닥과의 거리", wx.DefaultPosition, wx.DefaultSize, 0)
        self.alignment_distance_floor_txt.SetToolTip(u"어느 정도 손목과 바닥이 가까워졌을 때 손목과 바닥의 위치 맞춤을 실행할지 지정하십시오.\n값이 작을수록 손목과 바닥이 가까워졌을 때만 위치맞춤을 합니다.\n거리의 단위는 원 모델의 손바닥 크기입니다." \
                                                     + "\n사이징 실행 시 손목과 바닥 사이의 거리가 메시지란에 나와 있으니 참고해 주세요.\n슬라이더를 최대로 설정하면 항상 손목과 바닥을 정렬합니다.")
        self.alignment_distance_floor_txt.Wrap(-1)
        self.alignment_distance_floor_sizer.Add(self.alignment_distance_floor_txt, 0, wx.ALL, 5)

        self.alignment_distance_floor_label = wx.StaticText(self, wx.ID_ANY, u"（1.2）", wx.DefaultPosition, wx.DefaultSize, 0)
        self.alignment_distance_floor_label.SetToolTip(u"현재 지정된 손목과 바닥 사이의 거리입니다. 원모델의 양쪽 손목과 바닥과의 거리가 이 범위 내일 경우 손목과 바닥과의 위치맞춤을 실시합니다.")
        self.alignment_distance_floor_label.Wrap(-1)
        self.alignment_distance_floor_sizer.Add(self.alignment_distance_floor_label, 0, wx.ALL, 5)

        self.alignment_distance_floor_slider = FloatSliderCtrl(self, wx.ID_ANY, 1.2, 0, 10, 0.1, self.alignment_distance_floor_label, wx.DefaultPosition, wx.DefaultSize, wx.SL_HORIZONTAL)
        self.alignment_distance_floor_slider.Bind(wx.EVT_SCROLL_CHANGED, self.on_check_arm_process_alignment)
        self.alignment_distance_floor_sizer.Add(self.alignment_distance_floor_slider, 1, wx.ALL | wx.EXPAND, 5)

        self.sizer.Add(self.alignment_distance_floor_sizer, 0, wx.ALL | wx.EXPAND, 5)

        self.static_line04 = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        self.sizer.Add(self.static_line04, 0, wx.EXPAND | wx.ALL, 5)

        # Arm check skip--------------------
        self.arm_check_skip_sizer = wx.BoxSizer(wx.VERTICAL)

        self.arm_check_skip_flg_ctrl = wx.CheckBox(self, wx.ID_ANY, u"팔~손목 사이징 가능 체크 스킵하기", wx.DefaultPosition, wx.DefaultSize, 0)
        self.arm_check_skip_flg_ctrl.SetToolTip(u"사이징 가능 체크(팔 IK가 있으면 불가)를 건너뛰어 반드시 처리하도록 합니다.")
        self.arm_check_skip_sizer.Add(self.arm_check_skip_flg_ctrl, 0, wx.ALL, 5)

        self.arm_check_skip_description = wx.StaticText(self, wx.ID_ANY, u"팔 사이징 가능 체크(팔 IK가 있으면 불가)를 건너뛰고 반드시 팔 관계 처리를 하도록 합니다.\n" \
                                                        + "※사이징 결과가 이상해질 가능성이 있습니다만, 지원 대상에서 제외됩니다.", \
                                                        wx.DefaultPosition, wx.DefaultSize, 0)
        self.arm_check_skip_description.Wrap(-1)
        self.arm_check_skip_sizer.Add(self.arm_check_skip_description, 0, wx.ALL, 5)
        self.sizer.Add(self.arm_check_skip_sizer, 0, wx.ALL | wx.EXPAND, 5)

        self.fit()

    def get_avoidance_target(self):
        if len(self.bulk_avoidance_set_dict.keys()) > 0:
            # Bulk용 데이터가 있는 경우 우선 반환
            return self.bulk_avoidance_set_dict

        target = {}
        if self.arm_process_flg_avoidance.GetValue() == 0:
            return target

        # Set the selected rigid list to the input field (only if the hash is the same)
        if 1 in self.avoidance_set_dict and self.avoidance_set_dict[1].rep_choices:
            if self.avoidance_set_dict[1].equal_hashdigest(self.frame.file_panel_ctrl.file_set):
                target[0] = [self.avoidance_set_dict[1].rep_avoidance_names[n] for n in self.avoidance_set_dict[1].rep_choices.GetSelections()]
            else:
                logger.warning("【No.%s】접촉 회피 설정 후 파일 세트가 변경되었으므로 접촉 회피를 클리어합니다.", 1, decoration=MLogger.DECORATION_BOX)

        for set_no in list(self.avoidance_set_dict.keys())[1:]:
            if set_no in self.avoidance_set_dict and self.avoidance_set_dict[set_no].rep_choices:
                if len(self.frame.multi_panel_ctrl.file_set_list) >= set_no - 1 and self.avoidance_set_dict[set_no].equal_hashdigest(self.frame.multi_panel_ctrl.file_set_list[set_no - 2]):
                    target[set_no - 1] = [self.avoidance_set_dict[set_no].rep_avoidance_names[n] for n in self.avoidance_set_dict[set_no].rep_choices.GetSelections()]
                else:
                    logger.warning("【No.%s】접촉 회피 설정 후 파일 세트가 변경되었으므로 접촉 회피를 클리어합니다.", set_no, decoration=MLogger.DECORATION_BOX)

        return target

    def on_click_avoidance_target(self, event: wx.Event):
        if self.avoidance_dialog.ShowModal() == wx.ID_CANCEL:
            return     # the user changed their mind

        # Clear
        self.avoidance_target_txt_ctrl.SetValue("")

        # Set selected rigid body list to insert tab
        for set_no, set_data in self.avoidance_set_dict.items():
            # choice-by-choice wording
            if set_data.rep_choices:
                selections = [set_data.rep_choices.GetString(n) for n in set_data.rep_choices.GetSelections()]
                self.avoidance_target_txt_ctrl.WriteText("【No.{0}】{1}\n".format(set_no, ', '.join(selections)))

        self.arm_process_flg_avoidance.SetValue(1)
        self.avoidance_dialog.Hide()

    def initialize(self, event: wx.Event):

        if 1 in self.avoidance_set_dict:
            # If you have a file set to avoid contact for the file tab.
            if self.frame.file_panel_ctrl.file_set.is_loaded():
                # Hash check if already present
                if self.avoidance_set_dict[1].equal_hashdigest(self.frame.file_panel_ctrl.file_set):
                    # If same, pass
                    pass
                else:
                    # If not, reread the file set
                    self.add_set(1, self.frame.file_panel_ctrl.file_set, replace=True)
            else:
                # If the File Tab fails to load, Reread (clear)
                self.add_set(1, self.frame.file_panel_ctrl.file_set, replace=True)
        else:
            # See File Sets on the File Tab when creating from Empty
            self.add_set(1, self.frame.file_panel_ctrl.file_set, replace=False)

        # check multi as much as possible
        for multi_file_set_idx, multi_file_set in enumerate(self.frame.multi_panel_ctrl.file_set_list):
            set_no = multi_file_set_idx + 2
            if set_no in self.avoidance_set_dict:
                # Multiple Tabs Contact Avoidance File Set
                if multi_file_set.is_loaded():
                    # Hash check if already present
                    if self.avoidance_set_dict[set_no].equal_hashdigest(multi_file_set):
                        # If same, pass
                        pass
                    else:
                        # If not, reread the file set
                        self.add_set(set_no, multi_file_set, replace=True)

                        # if there are more than one, Change the default value
                        self.set_multi_initialize_value()
                else:
                    # if multiple tabs fail to load, Reread (clear)
                    self.add_set(set_no, multi_file_set, replace=True)

                    # if there are more than one, Change the default value .
                    self.set_multi_initialize_value()
            else:
                # See multi-tab file set when creating from empty
                self.add_set(set_no, multi_file_set, replace=False)

                # if there are more than one Change the default value
                self.set_multi_initialize_value()

        # unprocessable Arm type model name list
        disable_arm_model_names = []

        if self.frame.file_panel_ctrl.file_set.is_loaded():
            if not self.frame.file_panel_ctrl.file_set.org_model_file_ctrl.data.can_arm_sizing:
                # Add list if arm is not available
                disable_arm_model_names.append("【No.1】작성 원본 모델: {0}".format(self.frame.file_panel_ctrl.file_set.org_model_file_ctrl.data.name))

            if not self.frame.file_panel_ctrl.file_set.rep_model_file_ctrl.data.can_arm_sizing:
                # Add list if arm is not available
                disable_arm_model_names.append("【No.1】변환용 모델: {0}".format(self.frame.file_panel_ctrl.file_set.rep_model_file_ctrl.data.name))

        for multi_file_set_idx, multi_file_set in enumerate(self.frame.multi_panel_ctrl.file_set_list):
            set_no = multi_file_set_idx + 2
            if multi_file_set.is_loaded():
                if not multi_file_set.org_model_file_ctrl.data.can_arm_sizing:
                    # Add list if arm is not available
                    disable_arm_model_names.append("【No.{0}】작성 원본 모델: {1}".format(set_no, multi_file_set.org_model_file_ctrl.data.name))

                if not multi_file_set.rep_model_file_ctrl.data.can_arm_sizing:
                    # Add list if arm is not available
                    disable_arm_model_names.append("【No.{0}】변환용 모델: {1}".format(set_no, multi_file_set.rep_model_file_ctrl.data.name))

        if len(disable_arm_model_names) > 0 and not self.arm_check_skip_flg_ctrl.GetValue():
            # Dialog display if unprocessable arm type model is present
            with wx.MessageDialog(self, "아래 모델에 '팔 IK'와 유사한 문자열이 포함되어 있기 때문에 해당 파일 세트의 팔 계통 처리\n(팔 자세 보정, 비틀림 분산, 접촉 회피, 위치 맞춤)이 이대로는 패스됩니다.\n" \
                                  + "팔 체크 스킵 옵션을 ON하면 강제로 팔 계통 처리가 실행됩니다.\n※단, 결과가 이상해져도 지원 대상에서 제외됩니다.\n" \
                                  + "팔 체크 스킵 옵션 ON으로 하시겠습니까?？ \n\n{0}".format('\n'.join(disable_arm_model_names)), style=wx.YES_NO | wx.ICON_WARNING) as dialog:
                if dialog.ShowModal() == wx.ID_NO:
                    # Arm type chectk skip OFF
                    self.arm_check_skip_flg_ctrl.SetValue(0)
                else:
                    # Arm type chectk skip ON
                    self.arm_check_skip_flg_ctrl.SetValue(1)

        event.Skip()

    def set_multi_initialize_value(self):
        # Change the default wrist-to-wrist distance value if there are more than one occurrence
        self.alignment_distance_wrist_slider.SetValue(2.5)
        self.alignment_distance_wrist_label.SetLabel("（2.5）")

    def add_set(self, set_idx: int, file_set: SizingFileSet, replace: bool):
        new_avoidance_set = AvoidanceSet(self.frame, self, self.avoidance_dialog.scrolled_window, set_idx, file_set)
        if replace:
            # Replace
            self.avoidance_dialog.set_list_sizer.Hide(self.avoidance_set_dict[set_idx].set_sizer, recursive=True)
            self.avoidance_dialog.set_list_sizer.Replace(self.avoidance_set_dict[set_idx].set_sizer, new_avoidance_set.set_sizer, recursive=True)

            # If replace, Clear rigid list
            self.avoidance_target_txt_ctrl.SetValue("")
        else:
            # Add New
            self.avoidance_dialog.set_list_sizer.Add(new_avoidance_set.set_sizer, 0, wx.EXPAND | wx.ALL, 5)
        self.avoidance_set_dict[set_idx] = new_avoidance_set

        # Resize for scrollbar display
        self.avoidance_dialog.set_list_sizer.Layout()
        self.avoidance_dialog.set_list_sizer.FitInside(self.avoidance_dialog.scrolled_window)

    # VMD output file path generation
    def set_output_vmd_path(self, event, is_force=False):
        # Automatic output file path generation (set if empty) just in case
        self.frame.file_panel_ctrl.file_set.set_output_vmd_path(event)

        # Multi also auto-generated output file path (set if empty)
        for file_set in self.frame.multi_panel_ctrl.file_set_list:
            file_set.set_output_vmd_path(event)

    # What to do: Avoid contact ON
    def on_check_arm_process_avoidance(self, event: wx.Event):
        # Toggle text, check box, or real value if selected
        if isinstance(event.GetEventObject(), wx.StaticText):
            if self.arm_process_flg_avoidance.GetValue() == 0:
                self.arm_process_flg_avoidance.SetValue(1)
            else:
                self.arm_process_flg_avoidance.SetValue(0)

        # path regeneration
        self.set_output_vmd_path(event)

        event.Skip()

    # Processing target: Wrist alignment ON
    def on_check_arm_process_alignment(self, event: wx.Event):
        # Toggle text, check box, or real value if selected
        if isinstance(event.GetEventObject(), wx.StaticText):
            if self.arm_process_flg_alignment.GetValue() == 0:
                self.arm_process_flg_alignment.SetValue(1)
            else:
                self.arm_process_flg_alignment.SetValue(0)
        else:
            if self.arm_alignment_finger_flg_ctrl.GetValue() == 1 or self.arm_alignment_floor_flg_ctrl.GetValue() == 1:
                self.arm_process_flg_alignment.SetValue(1)

        if self.arm_alignment_finger_flg_ctrl.GetValue() and len(self.frame.multi_panel_ctrl.file_set_list) > 0:
            self.frame.on_popup_finger_warning(event)

        # path regeneration
        self.set_output_vmd_path(event)

        event.Skip()


class AvoidanceSet():

    def __init__(self, frame: wx.Frame, panel: wx.Panel, window: wx.Window, set_idx: int, file_set: SizingFileSet):
        self.frame = frame
        self.panel = panel
        self.window = window
        self.set_idx = set_idx
        self.file_set = file_set
        self.rep_model_digest = 0 if not file_set.rep_model_file_ctrl.data else file_set.rep_model_file_ctrl.data.digest
        self.rep_avoidances = ["머리 접촉회피(머리)"]   #  Option text
        self.rep_avoidance_names = ["머리 접촉 회피"]   # Rigid body name associated with option text
        self.rep_choices = None

        self.set_sizer = wx.StaticBoxSizer(wx.StaticBox(self.window, wx.ID_ANY, "【No.{0}】".format(set_idx)), orient=wx.VERTICAL)

        if file_set.is_loaded():
            self.model_name_txt = wx.StaticText(self.window, wx.ID_ANY, file_set.rep_model_file_ctrl.data.name[:15], wx.DefaultPosition, wx.DefaultSize, 0)
            self.model_name_txt.Wrap(-1)
            self.set_sizer.Add(self.model_name_txt, 0, wx.ALL, 5)

            for rigidbody_name, rigidbody in file_set.rep_model_file_ctrl.data.rigidbodies.items():
                # Rigid body to be processed: valid bone-following rigid body
                if rigidbody.isModeStatic() and rigidbody.bone_index in file_set.rep_model_file_ctrl.data.bone_indexes:
                    self.rep_avoidances.append("{0} ({1})".format(rigidbody.name, file_set.rep_model_file_ctrl.data.bone_indexes[rigidbody.bone_index]))
                    self.rep_avoidance_names.append(rigidbody.name)

            # selection control
            self.rep_choices = wx.ListBox(self.window, id=wx.ID_ANY, choices=self.rep_avoidances, style=wx.LB_MULTIPLE | wx.LB_NEEDED_SB, size=(-1, 220))
            # Head contact avoidance is selected by default
            self.rep_choices.SetSelection(0)
            self.set_sizer.Add(self.rep_choices, 0, wx.ALL, 5)

            # BATCH COPY BUTTON
            self.copy_btn_ctrl = wx.Button(self.window, wx.ID_ANY, u"일괄용 카피", wx.DefaultPosition, wx.DefaultSize, 0)
            self.copy_btn_ctrl.SetToolTip(u"접촉 회피 데이터를 일괄 CSV 형식에 맞게 클립보드에 복사합니다.")
            self.copy_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_copy)
            self.set_sizer.Add(self.copy_btn_ctrl, 0, wx.ALL, 5)
        else:
            self.no_data_txt = wx.StaticText(self.window, wx.ID_ANY, u"데이터 없음", wx.DefaultPosition, wx.DefaultSize, 0)
            self.no_data_txt.Wrap(-1)
            self.set_sizer.Add(self.no_data_txt, 0, wx.ALL, 5)

    def on_copy(self, event: wx.Event):
        # Morph Text Generation for Bulk CSV
        avoidance_txt_list = []
        for idx in self.rep_choices.GetSelections():
            avoidance_txt_list.append(f"{self.rep_avoidance_names[idx]}")
        # end-of-sentence semicolon
        avoidance_txt_list.append("")

        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(";".join(avoidance_txt_list)))
            wx.TheClipboard.Close()

        with wx.TextEntryDialog(self.frame, u"일괄 CSV용 접촉 회피 데이터를 출력합니다.\n" \
                                + "다이얼로그를 표시한 시점에서 이하의 접촉 회피 데이터가 클립보드에 복사되어 있습니다.\n" \
                                + "복사할 수 없었던 경우, 박스내의 문자열을 선택하고, CSV에 붙여 주세요.", caption=u"일괄 CSV용 접촉 회피 데이터",
                                value=";".join(avoidance_txt_list), style=wx.TextEntryDialogStyle, pos=wx.DefaultPosition) as dialog:
            dialog.ShowModal()

    # Check if it is the same as the hash in the current file set
    def equal_hashdigest(self, now_file_set: SizingFileSet):
        return self.rep_model_digest == now_file_set.rep_model_file_ctrl.data.digest


class AvoidanceDialog(wx.Dialog):

    def __init__(self, parent):
        super().__init__(parent, id=wx.ID_ANY, title="접촉 회피 강체 선택", pos=(-1, -1), size=(800, 500), style=wx.DEFAULT_DIALOG_STYLE, name="AvoidanceDialog")

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        # 説明文
        self.description_txt = wx.StaticText(self, wx.ID_ANY, u"손을 회피시키고 싶은 본 추종 강체를 변환처 모델로부터 선택할 수 있습니다.\n" \
                                             + u"'머리 접촉 회피'는 머리 크기를 자동 계산한 강체입니다.결과가 좋지 않은 경우는 선택을 제외해 주세요.\n" \
                                             + u"본 추종 강체라면 제한이 없지만, 너무 많은 강체를 선택하면 손이 어디에도 피하지 못하고, 뜻밖의 결과가 될 수 있습니다.", wx.DefaultPosition, wx.DefaultSize, 0)
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
                                                 wx.FULL_REPAINT_ON_RESIZE | wx.HSCROLL | wx.ALWAYS_SHOW_SB)
        self.scrolled_window.SetScrollRate(5, 5)

        # BASIC SIZER FOR RIGID BODY SET FOR CONTACT AVOIDANCE
        self.set_list_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Resize for scrollbar display
        self.scrolled_window.SetSizer(self.set_list_sizer)
        self.scrolled_window.Layout()
        self.sizer.Add(self.scrolled_window, 1, wx.ALL | wx.EXPAND, 5)
        self.SetSizer(self.sizer)
        self.sizer.Layout()

        # Show on screen center
        self.CentreOnScreen()

        # hide at first
        self.Hide()

