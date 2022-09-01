# -*- coding: utf-8 -*-
#
import os
import wx
import csv
import traceback

from form.panel.BasePanel import BasePanel
from form.parts.SizingFileSet import SizingFileSet
from utils import MFileUtils
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)


class MorphPanel(BasePanel):

    def __init__(self, frame: wx.Frame, parent: wx.Notebook, tab_idx: int):
        super().__init__(frame, parent, tab_idx)

        self.header_panel = wx.Panel(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.TAB_TRAVERSAL)
        self.header_sizer = wx.BoxSizer(wx.VERTICAL)

        self.description_txt = wx.StaticText(self.header_panel, wx.ID_ANY, "모프에 사용되는 모프를 변환 모델에 있는 임의의 모프로 대체할 수 있습니다.。" \
                                             + "\n모션 모프 풀다운의 선두 기호는 다음과 같습니다." \
                                             + "\n○　…　모션 생성 원본 모델·변환용 모델 전부에 있는 모프" \
                                             + "\n●　…　모션 변환용 모델에 있고, 생성 원본 모델에 없는 모프" \
                                             + "\n▲　…　모션 생성 원본 모델에 있고, 변환용 모델에 없는 모프", wx.DefaultPosition, wx.DefaultSize, 0)
        self.header_sizer.Add(self.description_txt, 0, wx.ALL, 5)

        self.header_panel.SetSizer(self.header_sizer)
        self.header_panel.Layout()
        self.sizer.Add(self.header_panel, 0, wx.EXPAND | wx.ALL, 5)

        # 모프セット(key: 파일セット番号, value: 모프セット)
        self.morph_set_dict = {}
        # Bulk用모프セット(key: 파일セット番号, value: 모프list)
        self.bulk_morph_set_dict = {}
        # 모프セット用基本Sizer
        self.set_list_sizer = wx.BoxSizer(wx.VERTICAL)

        self.scrolled_window = wx.ScrolledWindow(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, \
                                                 wx.FULL_REPAINT_ON_RESIZE | wx.VSCROLL | wx.ALWAYS_SHOW_SB)
        # self.scrolled_window.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DLIGHT))
        # self.scrolled_window.SetBackgroundColour("BLUE")
        self.scrolled_window.SetScrollRate(5, 5)

        # スクロールバーの表示のためにサイズ調整
        self.scrolled_window.SetSizer(self.set_list_sizer)
        self.scrolled_window.Layout()
        self.sizer.Add(self.scrolled_window, 1, wx.ALL | wx.EXPAND | wx.FIXED_MINSIZE, 5)
        self.sizer.Layout()
        self.fit()

    # 모프タブから모프치환リスト生成
    def get_morph_list(self, set_no: int, vmd_digest: str, org_model_digest: str, rep_model_digest: str):
        if set_no in self.bulk_morph_set_dict:
            # Bulk用の데이터がある場合、優先取得
            return self.bulk_morph_set_dict[set_no], (len(self.bulk_morph_set_dict[set_no]) > 0)
        elif set_no not in self.morph_set_dict:
            # そもそも登録がなければ何もなし
            return [], False
        else:
            morph_set = self.morph_set_dict[set_no]
            if morph_set.vmd_digest == vmd_digest and morph_set.org_model_digest == org_model_digest and morph_set.rep_model_digest == rep_model_digest:
                # あれば、そのNoの모프치환リスト
                return morph_set.get_morph_list(), True
            else:
                logger.warning("【No.%s】모프 치환 설정 후 파일 세트가 변경되었기 때문에 모프 치환을 클리어합니다.", set_no, decoration=MLogger.DECORATION_BOX)
                # ハッシュが一致してない場合空(設定されていた事だけ返す)
                return [], True

    # 모프タブ初期化処理
    def initialize(self, event: wx.Event):
        self.bulk_morph_set_dict = {}

        if 1 in self.morph_set_dict:
            # 파일タブ用모프の파일セットがある場合
            if self.frame.file_panel_ctrl.file_set.is_loaded():
                # 既にある場合、ハッシュチェック
                if self.morph_set_dict[1].equal_hashdigest(self.frame.file_panel_ctrl.file_set):
                    # 同じである場合、スルー
                    pass
                else:
                    # 違う場合、파일セット読み直し
                    self.add_set(1, self.frame.file_panel_ctrl.file_set, replace=True)
            else:
                # 파일タブが読み込み失敗している場合、読み直し（クリア）
                self.add_set(1, self.frame.file_panel_ctrl.file_set, replace=True)
        else:
            # 空から作る場合、파일タブの파일セット参照
            self.add_set(1, self.frame.file_panel_ctrl.file_set, replace=False)

        # multiはあるだけ調べる
        for multi_file_set_idx, multi_file_set in enumerate(self.frame.multi_panel_ctrl.file_set_list):
            set_no = multi_file_set_idx + 2
            if set_no in self.morph_set_dict:
                # 複数タブ用모프の파일セットがある場合
                if multi_file_set.is_loaded():
                    # 既にある場合、ハッシュチェック
                    if self.morph_set_dict[set_no].equal_hashdigest(multi_file_set):
                        # 同じである場合、スルー
                        pass
                    else:
                        # 違う場合、파일セット読み直し
                        self.add_set(set_no, multi_file_set, replace=True)
                else:
                    # 複数タブが読み込み失敗している場合、読み直し（クリア）
                    self.add_set(set_no, multi_file_set, replace=True)
            else:
                # 空から作る場合、複数タブの파일セット参照
                self.add_set(set_no, multi_file_set, replace=False)

    def add_set(self, set_idx: int, file_set: SizingFileSet, replace: bool, hide=False):
        new_morph_set = MorphSet(self.frame, self, self.scrolled_window, set_idx, file_set)
        if replace:
            # 置き換え
            self.set_list_sizer.Hide(self.morph_set_dict[set_idx].set_sizer, recursive=True)
            self.set_list_sizer.Replace(self.morph_set_dict[set_idx].set_sizer, new_morph_set.set_sizer, recursive=True)
        else:
            # 新規추가
            self.set_list_sizer.Add(new_morph_set.set_sizer, 0, wx.EXPAND | wx.ALL, 5)
        self.morph_set_dict[set_idx] = new_morph_set

        # スクロールバーの表示のためにサイズ調整
        self.set_list_sizer.Layout()
        self.set_list_sizer.FitInside(self.scrolled_window)

    # フォーム無効化
    def disable(self):
        self.file_set.disable()

    # フォーム無効化
    def enable(self):
        self.file_set.enable()


class MorphSet():

    def __init__(self, frame: wx.Frame, panel: wx.Panel, window: wx.Window, set_idx: int, file_set: SizingFileSet):
        self.frame = frame
        self.panel = panel
        self.window = window
        self.set_idx = set_idx
        self.file_set = file_set
        self.vmd_digest = 0 if not file_set.motion_vmd_file_ctrl.data else file_set.motion_vmd_file_ctrl.data.digest
        self.org_model_digest = 0 if not file_set.org_model_file_ctrl.data else file_set.org_model_file_ctrl.data.digest
        self.rep_model_digest = 0 if not file_set.rep_model_file_ctrl.data else file_set.rep_model_file_ctrl.data.digest
        self.org_morphs = [""]  # 選択肢文言
        self.rep_morphs = [""]
        self.org_choices = []   # 選択コントロール
        self.rep_choices = []
        self.org_morph_names = {}   # 選択肢文言に紐付く모프名
        self.rep_morph_names = {}
        self.org_buttons = []   # 関連ボタンコントロール
        self.rep_buttons = []
        self.ratios = []

        self.set_sizer = wx.StaticBoxSizer(wx.StaticBox(self.window, wx.ID_ANY, "【No.{0}】".format(set_idx)), orient=wx.VERTICAL)

        if file_set.is_loaded():
            for mk in file_set.motion_vmd_file_ctrl.data.morphs.keys():
                morph_fnos = file_set.motion_vmd_file_ctrl.data.get_morph_fnos(mk)
                for fno in morph_fnos:
                    if file_set.motion_vmd_file_ctrl.data.morphs[mk][fno].ratio != 0:
                        # キーが存在しており、かつ初期値ではない値が入っている場合、치환対象

                        if mk in file_set.rep_model_file_ctrl.data.morphs and file_set.rep_model_file_ctrl.data.morphs[mk].display:
                            if mk in file_set.org_model_file_ctrl.data.morphs and file_set.org_model_file_ctrl.data.morphs[mk].display:
                                # 作成元·치환先にある場合
                                txt = file_set.org_model_file_ctrl.data.morphs[mk].get_panel_name() + "○:" + mk[:10]
                                self.org_morphs.append(txt)
                                self.org_morph_names[txt] = mk
                            else:
                                # 作成元になくて·치환先にある場合
                                txt = "？●:" + mk[:10]
                                self.org_morphs.append(txt)
                                self.org_morph_names[txt] = mk
                        else:
                            if mk in file_set.org_model_file_ctrl.data.morphs and file_set.org_model_file_ctrl.data.morphs[mk].display:
                                # 作成元にあって、변환용にない場合
                                txt = file_set.org_model_file_ctrl.data.morphs[mk].get_panel_name() + "▲:" + mk[:10]
                                self.org_morphs.append(txt)
                                self.org_morph_names[txt] = mk
                            else:
                                # 作成元にも변환용にもない場合
                                txt = "？▲:" + mk[:10]
                                self.org_morphs.append(txt)
                                self.org_morph_names[txt] = mk

                        # 1件あればOK
                        break

            # 변환용は表示されている모프のみ対象とする
            for rmk, rmv in file_set.rep_model_file_ctrl.data.morphs.items():
                if rmv.display:
                    txt = rmv.get_panel_name() + ":" + rmk[:10]
                    self.rep_morphs.append(txt)
                    self.rep_morph_names[txt] = rmk

            self.btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

            # 一括用복사ボタン
            self.copy_btn_ctrl = wx.Button(self.window, wx.ID_ANY, u"일괄용 복사", wx.DefaultPosition, wx.DefaultSize, 0)
            self.copy_btn_ctrl.SetToolTip(u"모프 치환 데이터를 일괄 CSV 형식으로 맞추어 클립보드에 복사를 합니다.")
            self.copy_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_copy)
            self.btn_sizer.Add(self.copy_btn_ctrl, 0, wx.ALL, 5)

            # 임포트ボタン
            self.import_btn_ctrl = wx.Button(self.window, wx.ID_ANY, u"들여오기...", wx.DefaultPosition, wx.DefaultSize, 0)
            self.import_btn_ctrl.SetToolTip(u"모프 치환 데이터를 CSV 파일에서 읽습니다.\n파일 선택 대화상자가 열립니다.")
            self.import_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_import)
            self.btn_sizer.Add(self.import_btn_ctrl, 0, wx.ALL, 5)

            # エクスポートボタン
            self.export_btn_ctrl = wx.Button(self.window, wx.ID_ANY, u"내보내기...", wx.DefaultPosition, wx.DefaultSize, 0)
            self.export_btn_ctrl.SetToolTip(u"모프 치환 데이터를 CSV 파일에서 출력합니다.\n조정대상 VMD와 동일한 폴더로 출력합니다.")
            self.export_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_export)
            self.btn_sizer.Add(self.export_btn_ctrl, 0, wx.ALL, 5)

            # 行추가ボタン
            self.add_line_btn_ctrl = wx.Button(self.window, wx.ID_ANY, u"행 추가", wx.DefaultPosition, wx.DefaultSize, 0)
            self.add_line_btn_ctrl.SetToolTip(u"모프 치환의 맞춤 행을 추가합니다.\n 상한은 없습니다.")
            self.add_line_btn_ctrl.Bind(wx.EVT_BUTTON, self.on_add_line)
            self.btn_sizer.Add(self.add_line_btn_ctrl, 0, wx.ALL, 5)

            self.set_sizer.Add(self.btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

            # タイトル部分
            self.grid_sizer = wx.FlexGridSizer(0, 4, 0, 0)
            self.grid_sizer.SetFlexibleDirection(wx.BOTH)
            self.grid_sizer.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_SPECIFIED)

            # 모델名 ----------
            self.org_model_name_txt = wx.StaticText(self.window, wx.ID_ANY, file_set.org_model_file_ctrl.data.name[:15], wx.DefaultPosition, wx.DefaultSize, 0)
            self.org_model_name_txt.Wrap(-1)
            self.grid_sizer.Add(self.org_model_name_txt, 0, wx.ALL, 5)

            self.name_arrow_txt = wx.StaticText(self.window, wx.ID_ANY, u"　", wx.DefaultPosition, wx.DefaultSize, 0)
            self.name_arrow_txt.Wrap(-1)
            self.grid_sizer.Add(self.name_arrow_txt, 0, wx.CENTER | wx.ALL, 5)

            self.rep_model_name_txt = wx.StaticText(self.window, wx.ID_ANY, file_set.rep_model_file_ctrl.data.name[:15], wx.DefaultPosition, wx.DefaultSize, 0)
            self.rep_model_name_txt.Wrap(-1)
            self.grid_sizer.Add(self.rep_model_name_txt, 0, wx.ALL, 5)

            self.name_ratio_txt = wx.StaticText(self.window, wx.ID_ANY, u"　", wx.DefaultPosition, wx.DefaultSize, 0)
            self.name_ratio_txt.Wrap(-1)
            self.grid_sizer.Add(self.name_ratio_txt, 0, wx.CENTER | wx.ALL, 5)

            # ------------
            self.org_morph_txt = wx.StaticText(self.window, wx.ID_ANY, u"모션 모프", wx.DefaultPosition, wx.DefaultSize, 0)
            self.org_morph_txt.SetToolTip(u"조정 대상 VMD/VPD에 등록되어있는 모프입니다.")
            self.org_morph_txt.Wrap(-1)
            self.grid_sizer.Add(self.org_morph_txt, 0, wx.ALL, 5)

            self.arrow_txt = wx.StaticText(self.window, wx.ID_ANY, u"　→　", wx.DefaultPosition, wx.DefaultSize, 0)
            self.arrow_txt.Wrap(-1)
            self.grid_sizer.Add(self.arrow_txt, 0, wx.CENTER | wx.ALL, 5)

            self.rep_morph_txt = wx.StaticText(self.window, wx.ID_ANY, u"치환후 모프", wx.DefaultPosition, wx.DefaultSize, 0)
            self.rep_morph_txt.SetToolTip(u"모션 변환용 모델에서 정의된 모프입니다.")
            self.rep_morph_txt.Wrap(-1)
            self.grid_sizer.Add(self.rep_morph_txt, 0, wx.ALL, 5)

            self.ratio_title_txt = wx.StaticText(self.window, wx.ID_ANY, u"크기 보정", wx.DefaultPosition, wx.DefaultSize, 0)
            self.ratio_title_txt.SetToolTip(u"치환후 모프의 크기를 보정합니다.")
            self.ratio_title_txt.Wrap(-1)
            self.grid_sizer.Add(self.ratio_title_txt, 0, wx.ALL, 5)

            # 一行추가
            self.add_line()

            self.set_sizer.Add(self.grid_sizer, 0, wx.ALL, 5)
        else:
            self.no_data_txt = wx.StaticText(self.window, wx.ID_ANY, u"데이터 없음", wx.DefaultPosition, wx.DefaultSize, 0)
            self.no_data_txt.Wrap(-1)
            self.set_sizer.Add(self.no_data_txt, 0, wx.ALL, 5)

    def get_morph_list(self):
        morph_list = []

        for midx, (oc, rc, ratio) in enumerate(zip(self.org_choices, self.rep_choices, self.ratios)):
            if oc.GetSelection() > 0 and rc.GetSelection() > 0:
                # なんか設定されていたら対象

                # プレフィックスを除去
                om = self.org_morph_names[oc.GetString(oc.GetSelection())]
                rm = self.rep_morph_names[rc.GetString(rc.GetSelection())]
                r = ratio.GetValue()

                if (om, rm, r) not in morph_list:
                    # 모프ペアがまだ登録されてないければ登録
                    morph_list.append((om, rm, r))

        # どれも設定されていなければFalse
        return morph_list

    def add_line(self):
        # 치환前모프
        self.org_choices.append(wx.Choice(self.window, id=wx.ID_ANY, choices=self.org_morphs))
        self.org_choices[-1].Bind(wx.EVT_CHOICE, lambda event: self.on_change_choice(event, len(self.org_choices) - 1))
        self.grid_sizer.Add(self.org_choices[-1], 0, wx.ALL, 5)

        # 矢印
        self.arrow_txt = wx.StaticText(self.window, wx.ID_ANY, u"　→　", wx.DefaultPosition, wx.DefaultSize, 0)
        self.arrow_txt.Wrap(-1)
        self.grid_sizer.Add(self.arrow_txt, 0, wx.CENTER | wx.ALL, 5)

        # 치환後모프
        self.rep_choices.append(wx.Choice(self.window, id=wx.ID_ANY, choices=self.rep_morphs))
        self.rep_choices[-1].Bind(wx.EVT_CHOICE, lambda event: self.on_change_choice(event, len(self.rep_choices) - 1))
        self.grid_sizer.Add(self.rep_choices[-1], 0, wx.ALL, 5)

        # 大きさ比率
        self.ratios.append(wx.SpinCtrlDouble(self.window, id=wx.ID_ANY, size=wx.Size(80, -1), value="1.0", min=-10, max=10, initial=1.0, inc=0.01))
        self.ratios[-1].Bind(wx.EVT_MOUSEWHEEL, lambda event: self.frame.on_wheel_spin_ctrl(event, 0.05))
        self.grid_sizer.Add(self.ratios[-1], 0, wx.ALL, 5)

        # スクロールバーの表示のためにサイズ調整
        self.panel.set_list_sizer.Layout()
        self.panel.set_list_sizer.FitInside(self.panel.scrolled_window)

    # 모프が設定されているか
    def is_set_morph(self):
        for midx, (oc, rc) in enumerate(zip(self.org_choices, self.rep_choices)):
            if oc.GetSelection() > 0 and rc.GetSelection() > 0:
                # なんか設定されていたらOK
                return True

        # どれも設定されていなければFalse
        return False

    def on_change_choice(self, event: wx.Event, midx: int):
        # 選択肢を変えた場合、まずパス変更
        self.file_set.set_output_vmd_path(event)

        # 最後である場合、行추가
        if midx == len(self.org_choices) - 1 and self.org_choices[midx].GetSelection() > 0 and self.rep_choices[midx].GetSelection() > 0:
            self.add_line()

    # 現在の파일セットのハッシュと同じであるかチェック
    def equal_hashdigest(self, now_file_set: SizingFileSet):
        return self.vmd_digest == now_file_set.motion_vmd_file_ctrl.data.digest \
            and self.org_model_digest == now_file_set.org_model_file_ctrl.data.digest \
            and self.rep_model_digest == now_file_set.rep_model_file_ctrl.data.digest

    def on_copy(self, event: wx.Event):
        # 一括CSV用모프テキスト生成
        morph_txt_list = []
        morph_list = self.get_morph_list()
        for (om, rm, r) in morph_list:
            morph_txt_list.append(f"{om}:{rm}:{r}")
        # 文末セミコロン
        morph_txt_list.append("")

        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(";".join(morph_txt_list)))
            wx.TheClipboard.Close()

        with wx.TextEntryDialog(self.frame, u"일괄 CSV용의 모프 데이터를 출력합니다.\n" \
                                + "다이얼로그를 표시한 시점에서 아래 모프데이터가 클립보드에 복사됩니다.\n" \
                                + "복사되지 않았을 경우, 상자 안의 문자열을 선택하여 CSV에 붙여 주십시오.", caption=u"일괄 CSV용 모프 데이터",
                                value=";".join(morph_txt_list), style=wx.TextEntryDialogStyle, pos=wx.DefaultPosition) as dialog:
            dialog.ShowModal()

    def on_import(self, event: wx.Event):
        input_morph_path = MFileUtils.get_output_morph_path(
            self.file_set.motion_vmd_file_ctrl.file_ctrl.GetPath(),
            self.file_set.org_model_file_ctrl.file_ctrl.GetPath(),
            self.file_set.rep_model_file_ctrl.file_ctrl.GetPath()
        )

        with wx.FileDialog(self.frame, "모프 맞추기 CSV 읽기", wildcard=u"CSV파일 (*.csv)|*.csv|전체 파일 (*.*)|*.*",
                           defaultDir=os.path.dirname(input_morph_path),
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:

            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return     # the user changed their mind

            # Proceed loading the file chosen by the user
            target_morph_path = fileDialog.GetPath()
            try:
                with open(target_morph_path, 'r') as f:
                    cr = csv.reader(f, delimiter=",", quotechar='"')
                    morph_lines = [row for row in cr]

                    if len(morph_lines) == 0:
                        return

                    org_choice_values = morph_lines[0]
                    rep_choice_values = morph_lines[1]
                    rep_rate_values = morph_lines[2]

                    logger.debug("org_choice_values: %s", org_choice_values)
                    logger.debug("rep_choice_values: %s", rep_choice_values)
                    logger.debug("rep_rate_values: %s", rep_rate_values)

                    if len(org_choice_values) == 0 or len(rep_choice_values) == 0 or len(rep_rate_values) == 0:
                        return

                    for vcv, rcv, rrv in zip(org_choice_values, rep_choice_values, rep_rate_values):
                        vc = self.org_choices[-1]
                        rc = self.rep_choices[-1]
                        rr = self.ratios[-1]
                        # 全件なめる
                        for v, c in [(vcv, vc), (rcv, rc)]:
                            logger.debug("v: %s, c: %s", v, c)
                            is_seted = False
                            for n in range(c.GetCount()):
                                for p in ["눈", "눈썹", "입", "기타", "?"]:
                                    for s in ["", "○", "●", "▲"]:
                                        # パネル情報を含める
                                        txt = "{0}{1}:{2}".format(p, s, v[:10])
                                        # if v == vcv:
                                        # 	logger.debug("txt: %s, c.GetString(n): %s", txt, c.GetString(n))
                                        if c.GetString(n).strip() == txt:
                                            logger.debug("[HIT] txt: %s, c.GetString(n): %s, n: %s", txt, c.GetString(n), n)
                                            # パネルと모프名で一致している場合、採用
                                            c.SetSelection(n)
                                            is_seted = True
                                            break
                                    if is_seted:
                                        break
                        # 大きさ補正を設定する
                        try:
                            rr.SetValue(float(rrv))
                        except Exception:
                            pass

                        # 行추가
                        self.add_line()

                # パス変更
                self.file_set.set_output_vmd_path(event)

            except Exception:
                dialog = wx.MessageDialog(self.frame, "CSV파일을 읽을 수 없었습니다. '%s'\n\n%s." % (target_morph_path, traceback.format_exc()), style=wx.OK)
                dialog.ShowModal()
                dialog.Destroy()

    def on_export(self, event: wx.Event):
        org_morph_list = []
        rep_morph_list = []
        ratio_list = []
        for m in self.get_morph_list():
            org_morph_list.append(m[0])
            rep_morph_list.append(m[1])
            ratio_list.append(m[2])

        output_morph_path = MFileUtils.get_output_morph_path(
            self.file_set.motion_vmd_file_ctrl.file_ctrl.GetPath(),
            self.file_set.org_model_file_ctrl.file_ctrl.GetPath(),
            self.file_set.rep_model_file_ctrl.file_ctrl.GetPath()
        )

        try:
            with open(output_morph_path, encoding='cp932', mode='w', newline='') as f:
                cw = csv.writer(f, delimiter=",", quotechar='"', quoting=csv.QUOTE_ALL)

                # 元모프行
                cw.writerow(org_morph_list)
                # 先모프行
                cw.writerow(rep_morph_list)
                # 大きさ
                cw.writerow(ratio_list)

            logger.info("출력 성공: %s" % output_morph_path)

            dialog = wx.MessageDialog(self.frame, "모프 데이터 내보내기에 성공했습니다. \n'%s'" % (output_morph_path), style=wx.OK)
            dialog.ShowModal()
            dialog.Destroy()

        except Exception:
            dialog = wx.MessageDialog(self.frame, "모프 데이터 내보내기에 실패했습니다. \n'%s'\n\n%s." % (output_morph_path, traceback.format_exc()), style=wx.OK)
            dialog.ShowModal()
            dialog.Destroy()

    def on_add_line(self, event: wx.Event):
        # 行추가
        self.add_line()

