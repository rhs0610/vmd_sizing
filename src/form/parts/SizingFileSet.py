# -*- coding: utf-8 -*-
#
import os
import wx
import wx.lib.newevent

from form.parts.BaseFilePickerCtrl import BaseFilePickerCtrl
from form.parts.HistoryFilePickerCtrl import HistoryFilePickerCtrl
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from mmd.PmxData import PmxModel
from utils import MServiceUtils, MFileUtils # noqa
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)


class SizingFileSet():

    def __init__(self, frame: wx.Frame, panel: wx.Panel, file_hitories: dict, set_no):
        self.file_hitories = file_hitories
        self.frame = frame
        self.panel = panel
        self.set_no = set_no
        self.STANCE_DETAIL_CHOICES = ["센터 XZ 보정", "상반신 보정", "하반신 보정", "발 IK 보정", "발끝 보정", "발끝 IK 보정", "어깨 보정", "센터 Y 보정"]
        self.selected_stance_details = [0, 1, 2, 4, 5, 6, 7]

        if self.set_no == 1:
            # 파일パネルのはそのまま추가
            self.set_sizer = wx.BoxSizer(wx.VERTICAL)
        else:
            self.set_sizer = wx.StaticBoxSizer(wx.StaticBox(self.panel, wx.ID_ANY, "【No.{0}】".format(set_no)), orient=wx.VERTICAL)

        able_aster_toottip = "파일명에 별표（*）를 사용하면 여러개의 데이터를 한 번에 사이징할 수 있습니다." if self.set_no == 1 else "일괄지정은 할 수 없습니다."
        # VMD/VPD파일コントロール
        self.motion_vmd_file_ctrl = HistoryFilePickerCtrl(frame, panel, u"조정 대상 모션VMD/VPD", u"조정 대상 모션VMD/VPD파일 열기", ("vmd", "vpd"), wx.FLP_DEFAULT_STYLE, \
                                                          u"조정하고싶은 모션의 VMD/VPD 경로를 지정해 주세요. \nD&D에서의 지정, 열기 버튼에서의 지정, 기록에서의 선택이 가능합니다.\n{0}".format(able_aster_toottip), \
                                                          file_model_spacer=46, title_parts_ctrl=None, title_parts2_ctrl=None, file_histories_key="vmd", is_change_output=True, \
                                                          is_aster=True, is_save=False, set_no=set_no)
        self.set_sizer.Add(self.motion_vmd_file_ctrl.sizer, 1, wx.EXPAND, 0)

        # 作成元の자세詳細再現FLG
        detail_stance_flg_ctrl = wx.CheckBox(panel, wx.ID_ANY, u"자세 추가 보정", wx.DefaultPosition, wx.DefaultSize, 0)
        detail_stance_flg_ctrl.SetToolTip(u"체크를 하면, 세부 자세 보정을 추가로 진행할 수 있습니다.\n자세한 보정 내용은 옆의 '*' 버튼을 눌러보세요.")
        detail_stance_flg_ctrl.Bind(wx.EVT_CHECKBOX, self.set_output_vmd_path)

        # 자세보정
        detail_btn_ctrl = wx.Button(panel, wx.ID_ANY, u"＊", wx.DefaultPosition, (20, 20), 0)
        detail_btn_ctrl.SetToolTip("자세 추가 보정의 내역 확인 및 취사선택을 할 수 있습니다.")
        detail_btn_ctrl.Bind(wx.EVT_BUTTON, self.select_detail)

        # 作成元PMX파일コントロール
        self.org_model_file_ctrl = HistoryFilePickerCtrl(frame, panel, u"모션 작성 원본 모델PMX", u"모션 작성 원본 PMX파일 열기", ("pmx"), wx.FLP_DEFAULT_STYLE, \
                                                         u"모션 작성에 사용된 모델의 PMX 경로를 지정해주세요.\n정밀도는 떨어지지만, 유사한 사이즈, 본 구조의 모델로도 대용할 수 있습니다.\nD&D에서의 지정, 열기 버튼에서의 지정, 기록 중에서 선택을 할 수 있습니다.", \
                                                         file_model_spacer=1, title_parts_ctrl=detail_stance_flg_ctrl, title_parts2_ctrl=detail_btn_ctrl, \
                                                         file_histories_key="org_pmx", is_change_output=False, is_aster=False, is_save=False, set_no=set_no)
        self.set_sizer.Add(self.org_model_file_ctrl.sizer, 1, wx.EXPAND, 0)

        # 비틀림분산추가FLG
        twist_flg_ctrl = wx.CheckBox(panel, wx.ID_ANY, u"비틀림 분산 있음", wx.DefaultPosition, wx.DefaultSize, 0)
        twist_flg_ctrl.SetToolTip(u"체크하면, 팔 비틀림 등에 대한 분산 처리를 추가할 수 있습니다.\n시간이 걸립니다.")
        twist_flg_ctrl.Bind(wx.EVT_CHECKBOX, self.set_output_vmd_path)

        # 変換先PMX파일コントロール
        self.rep_model_file_ctrl = HistoryFilePickerCtrl(frame, panel, u"모션 변환용 모델PMX", u"모션 변환용 모델 PMX파일 열기", ("pmx"), wx.FLP_DEFAULT_STYLE, \
                                                         u"실제로 모션을 읽고싶은 모델의 PMX 경로를 지정해주세요.\nD&D에서의 지정, 열기 버튼에서의 지정, 기록 중에서 선택을 할 수 있습니다.", \
                                                         file_model_spacer=18, title_parts_ctrl=twist_flg_ctrl, title_parts2_ctrl=None, file_histories_key="rep_pmx", \
                                                         is_change_output=True, is_aster=False, is_save=False, set_no=set_no)
        self.set_sizer.Add(self.rep_model_file_ctrl.sizer, 1, wx.EXPAND, 0)

        # 출력先VMD파일コントロール
        self.output_vmd_file_ctrl = BaseFilePickerCtrl(frame, panel, u"출력 VMD", u"출 력VMD파일 열기", ("vmd"), wx.FLP_OVERWRITE_PROMPT | wx.FLP_SAVE | wx.FLP_USE_TEXTCTRL, \
                                                       u"조정 결과의 VMD 력 패스를 지정해 주세요.\nVMD 파일과 변환용 PMX 파일명에 따라 자동 생성 되지만 임의 경로로 변경할 수 있습니다.", \
                                                       is_aster=False, is_save=True, set_no=set_no)
        self.set_sizer.Add(self.output_vmd_file_ctrl.sizer, 1, wx.EXPAND, 0)

    def get_selected_stance_details(self):
        # 선택されたINDEXの名称を返す
        return [self.STANCE_DETAIL_CHOICES[n] for n in self.selected_stance_details]

    def select_detail(self, event: wx.Event):

        with wx.MultiChoiceDialog(self.panel, "자세 추가 보정의 사이에, 체크한 보정만 실시합니다.", caption="자세 추가 보정 선택", \
                                  choices=self.STANCE_DETAIL_CHOICES, style=wx.CHOICEDLG_STYLE) as choiceDialog:

            choiceDialog.SetSelections(self.selected_stance_details)

            if choiceDialog.ShowModal() == wx.ID_CANCEL:
                return     # the user changed their mind

            self.selected_stance_details = choiceDialog.GetSelections()

            if len(self.selected_stance_details) == 0:
                self.org_model_file_ctrl.title_parts_ctrl.SetValue(0)
            else:
                self.org_model_file_ctrl.title_parts_ctrl.SetValue(1)

    def save(self):
        self.motion_vmd_file_ctrl.save()
        self.org_model_file_ctrl.save()
        self.rep_model_file_ctrl.save()

    # フォーム無効化
    def disable(self):
        self.motion_vmd_file_ctrl.disable()
        self.org_model_file_ctrl.disable()
        self.rep_model_file_ctrl.disable()
        self.output_vmd_file_ctrl.disable()

    # フォーム無効化
    def enable(self):
        self.motion_vmd_file_ctrl.enable()
        self.org_model_file_ctrl.enable()
        self.rep_model_file_ctrl.enable()
        self.output_vmd_file_ctrl.enable()

    # 파일読み込み前の체크
    def is_valid(self):
        result = True
        if self.set_no == 1:
            # 1番目は必ず調べる
            result = self.motion_vmd_file_ctrl.is_valid() and result
            result = self.org_model_file_ctrl.is_valid() and result
            result = self.rep_model_file_ctrl.is_valid() and result
            result = self.output_vmd_file_ctrl.is_valid() and result
        else:
            # 2番目以降は, 파일が揃ってたら調べる
            if self.motion_vmd_file_ctrl.is_set_path() or self.org_model_file_ctrl.is_set_path() or \
               self.rep_model_file_ctrl.is_set_path() or self.output_vmd_file_ctrl.is_set_path():
                result = self.motion_vmd_file_ctrl.is_valid() and result
                result = self.org_model_file_ctrl.is_valid() and result
                result = self.rep_model_file_ctrl.is_valid() and result
                result = self.output_vmd_file_ctrl.is_valid() and result

        return result

    # 入力後の入力可否체크
    def is_loaded_valid(self):
        if self.set_no == 0:
            # CSVとかの파일は番号출력なし
            display_set_no = ""
        else:
            display_set_no = "{0}번째의".format(self.set_no)

        # 両方のPMXが読めて, 모션も読み込めた場合, キー체크
        not_org_standard_bones = []
        not_org_other_bones = []
        not_org_morphs = []
        not_rep_standard_bones = []
        not_rep_other_bones = []
        not_rep_morphs = []
        mismatch_bones = []

        motion = self.motion_vmd_file_ctrl.data
        org_pmx = self.org_model_file_ctrl.data
        rep_pmx = self.rep_model_file_ctrl.data

        if not motion or not org_pmx or not rep_pmx:
            # どれか読めてなければそのまま終了
            return True

        if motion.motion_cnt == 0:
            logger.warning("%s본 모션 데이터에 키 프레임이 등록되어 있지 않습니다.", display_set_no, decoration=MLogger.DECORATION_BOX)
            return True

        result = True
        is_warning = False

        # 본
        for k in motion.bones.keys():
            bone_fnos = motion.get_bone_fnos(k)
            for fno in bone_fnos:
                if motion.bones[k][fno].position != MVector3D() or motion.bones[k][fno].rotation != MQuaternion():
                    # キーが存在しており, かつ初期値ではない値が入っている場合, 警告対象

                    if isinstance(org_pmx, Exception):
                        raise org_pmx

                    if k not in org_pmx.bones:
                        if k in PmxModel.PARENT_BORN_PAIR:
                            not_org_standard_bones.append(k)
                        else:
                            not_org_other_bones.append(k)

                    if isinstance(rep_pmx, Exception):
                        raise rep_pmx

                    if k not in rep_pmx.bones:
                        if k in PmxModel.PARENT_BORN_PAIR:
                            not_rep_standard_bones.append(k)
                        else:
                            not_rep_other_bones.append(k)

                    if k in org_pmx.bones and k in rep_pmx.bones:
                        mismatch_types = []
                        # 両方に본がある場合, フラグが同じであるか체크
                        if org_pmx.bones[k].getRotatable() != rep_pmx.bones[k].getRotatable():
                            mismatch_types.append("성능:회전")
                        if org_pmx.bones[k].getTranslatable() != rep_pmx.bones[k].getTranslatable():
                            mismatch_types.append("성능:이동")
                        if org_pmx.bones[k].getIkFlag() != rep_pmx.bones[k].getIkFlag():
                            mismatch_types.append("성능:IK")
                        if org_pmx.bones[k].getVisibleFlag() != rep_pmx.bones[k].getVisibleFlag():
                            mismatch_types.append("성능:표시")
                        if org_pmx.bones[k].getManipulatable() != rep_pmx.bones[k].getManipulatable():
                            mismatch_types.append("성능:조작")
                        if org_pmx.bones[k].display != rep_pmx.bones[k].display:
                            mismatch_types.append("표시 범위")

                        if len(mismatch_types) > 0:
                            mismatch_bones.append(f"{k} 　【차이】{', '.join(mismatch_types)}）")

                    # 1件あればOK
                    break

        for k in motion.morphs.keys():
            morph_fnos = motion.get_morph_fnos(k)
            for fno in morph_fnos:
                if motion.morphs[k][fno].ratio != 0:
                    # キーが存在しており, かつ初期値ではない値が入っている場合, 警告対象

                    if k not in org_pmx.morphs:
                        not_org_morphs.append(k)

                    if k not in rep_pmx.morphs:
                        not_rep_morphs.append(k)

                    # 1件あればOK
                    break

        if len(not_org_standard_bones) > 0 or len(not_org_other_bones) > 0 or len(not_org_morphs) > 0:
            logger.warning("%s%s에, 모션에 사용되는 모프가 부족합니다.\n 모델: %s\n 부족 본(준표준까지): %s\n 부족본(기타): %s\n 부족 모프: %s", \
                           display_set_no, self.org_model_file_ctrl.title, org_pmx.name, ",".join(not_org_standard_bones), ",".join(not_org_other_bones), ",".join(not_org_morphs), decoration=MLogger.DECORATION_BOX)
            is_warning = True

        if len(not_rep_standard_bones) > 0 or len(not_rep_other_bones) > 0 or len(not_rep_morphs) > 0:
            logger.warning("%s%s에, 모션에 사용되는 모프가 부족합니다.\n 모델: %s\n 부족 본(준표준까지): %s\n 부족본(기타): %s\n 부족 모프: %s", \
                           display_set_no, self.rep_model_file_ctrl.title, rep_pmx.name, ",".join(not_rep_standard_bones), ",".join(not_rep_other_bones), ",".join(not_rep_morphs), decoration=MLogger.DECORATION_BOX)
            is_warning = True

        if len(mismatch_bones) > 0:
            logger.warning("%s%s에, 모에 사용되는 본의 성능 등이 다릅니다.\n모델: %s\n다른 본:\n　%s", \
                           display_set_no, self.rep_model_file_ctrl.title, rep_pmx.name, "\n　".join(mismatch_bones), decoration=MLogger.DECORATION_BOX)
            is_warning = True

        if not is_warning:
            logger.info("모션에 사용되는 본·모프가 갖추어져 있습니다.", decoration=MLogger.DECORATION_BOX, title="OK")

        return result

    def is_loaded(self):
        result = True
        if self.is_valid():
            result = self.motion_vmd_file_ctrl.data and result
            result = self.org_model_file_ctrl.data and result
            result = self.rep_model_file_ctrl.data and result
        else:
            result = False

        return result

    def load(self):
        result = True
        try:
            is_check = not self.frame.arm_panel_ctrl.arm_check_skip_flg_ctrl.GetValue()
            result = self.motion_vmd_file_ctrl.load(is_check=is_check) and result
            result = self.org_model_file_ctrl.load(is_check=is_check) and result
            result = self.rep_model_file_ctrl.load(is_check=is_check) and result
        except Exception:
            result = False

        return result

    # VMD출력파일パス生成
    def set_output_vmd_path(self, event, is_force=False):
        output_vmd_path = MFileUtils.get_output_vmd_path(
            self.motion_vmd_file_ctrl.file_ctrl.GetPath(),
            self.rep_model_file_ctrl.file_ctrl.GetPath(),
            self.org_model_file_ctrl.title_parts_ctrl.GetValue(),
            self.rep_model_file_ctrl.title_parts_ctrl.GetValue(),
            self.frame.arm_panel_ctrl.arm_process_flg_avoidance.GetValue(),
            self.frame.arm_panel_ctrl.arm_process_flg_alignment.GetValue(),
            (self.set_no in self.frame.morph_panel_ctrl.morph_set_dict and self.frame.morph_panel_ctrl.morph_set_dict[self.set_no].is_set_morph()) \
            or (self.set_no in self.frame.morph_panel_ctrl.bulk_morph_set_dict and len(self.frame.morph_panel_ctrl.bulk_morph_set_dict[self.set_no]) > 0),
            self.output_vmd_file_ctrl.file_ctrl.GetPath(), is_force)

        self.output_vmd_file_ctrl.file_ctrl.SetPath(output_vmd_path)

        if len(output_vmd_path) >= 255 and os.name == "nt":
            logger.error("생성 예정인 파일 경로가 Windows 제한을 초과했습니다.\n 생성 예정 경로: {0}".format(output_vmd_path), decoration=MLogger.DECORATION_BOX)

    def calc_leg_ik_ratio(self):
        target_bones = ["左足", "左ひざ", "左足首", "センター"]

        if self.is_loaded() and set(target_bones).issubset(self.org_model_file_ctrl.data.bones) and set(target_bones).issubset(self.rep_model_file_ctrl.data.bones):
            # 頭身
            _, _, org_heads_tall = MServiceUtils.calc_heads_tall(self.org_model_file_ctrl.data)
            _, _, rep_heads_tall = MServiceUtils.calc_heads_tall(self.rep_model_file_ctrl.data)

            # 頭身比率
            heads_tall_ratio = org_heads_tall / rep_heads_tall

            # XZ比率(足の長さ)
            org_leg_length = ((self.org_model_file_ctrl.data.bones["左足首"].position - self.org_model_file_ctrl.data.bones["左ひざ"].position) \
                              + (self.org_model_file_ctrl.data.bones["左ひざ"].position - self.org_model_file_ctrl.data.bones["左足"].position)).length()
            rep_leg_length = ((self.rep_model_file_ctrl.data.bones["左足首"].position - self.rep_model_file_ctrl.data.bones["左ひざ"].position) \
                              + (self.rep_model_file_ctrl.data.bones["左ひざ"].position - self.rep_model_file_ctrl.data.bones["左足"].position)).length()
            logger.test("xz_ratio rep_leg_length: %s, org_leg_length: %s", rep_leg_length, org_leg_length)
            xz_ratio = 1 if org_leg_length == 0 else (rep_leg_length / org_leg_length)

            # Y比率(股下のY差)
            rep_leg_length = (self.rep_model_file_ctrl.data.bones["左足首"].position - self.rep_model_file_ctrl.data.bones["左足"].position).y()
            org_leg_length = (self.org_model_file_ctrl.data.bones["左足首"].position - self.org_model_file_ctrl.data.bones["左足"].position).y()
            logger.test("y_ratio rep_leg_length: %s, org_leg_length: %s", rep_leg_length, org_leg_length)
            y_ratio = 1 if org_leg_length == 0 else (rep_leg_length / org_leg_length)

            return xz_ratio, y_ratio, heads_tall_ratio


        return 1, 1, 1
