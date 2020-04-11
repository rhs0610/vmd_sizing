# -*- coding: utf-8 -*-
#

import copy

from mmd.PmxData import PmxModel # noqa
from mmd.VmdData import VmdMotion, VmdBoneFrame, VmdCameraFrame, VmdInfoIk, VmdLightFrame, VmdMorphFrame, VmdShadowFrame, VmdShowIkFrame # noqa
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from module.MOptions import MOptions, MOptionsDataSet
from module.MParams import BoneLinks
from utils import MUtils, MServiceUtils, MBezierUtils # noqa
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__, level=1)


class StanceService():
    def __init__(self, options: MOptions):
        self.options = options

    def execute(self):
        for data_set_idx, data_set in enumerate(self.options.data_set_list):
            if data_set.motion.motion_cnt <= 0:
                # モーションデータが無い場合、処理スキップ
                continue
            
            # 代替モデルでない場合
            if not data_set.substitute_model_flg:
                # センタースタンス補正
                self.adjust_center_stance(data_set_idx, data_set)

                # 上半身スタンス補正
                self.adjust_upper_stance(data_set_idx, data_set)
            
                # つま先補正
                self.adjust_toe_stance(data_set_idx, data_set)

            # 腕系サイジング可能であれば、腕スタンス補正
            if data_set.org_model.can_arm_sizing and data_set.rep_model.can_arm_sizing:
                if not data_set.substitute_model_flg:
                    # 肩スタンス補正
                    self.adjust_shoulder_stance(data_set_idx, data_set)

                # if data_set.twist_flg:
                #     # 捩り分散あり
                #     self.spread_twist(data_set_idx, data_set)
                
                # 腕スタンス補正
                self.adjust_arm_stance(data_set_idx, data_set)
            else:
                target_model_type = ""

                if not data_set.org_model.can_arm_sizing:
                    target_model_type = "作成元"

                if not data_set.rep_model.can_arm_sizing:
                    if len(target_model_type) > 0:
                        target_model_type = target_model_type + "/"
                    
                    target_model_type = target_model_type + "変換先"

                logger.warning("%sモデルの腕構造にサイジングが対応していない為、腕系処理をスキップします。", target_model_type, decoration=MLogger.DECORATION_BOX)

        return True
    
    # 捩り分散
    def spread_twist(self, data_set_idx: int, data_set: MOptionsDataSet):
        logger.info("捩り分散　【No.%s】", (data_set_idx + 1), decoration=MLogger.DECORATION_LINE)

        for direction in ["左", "右"]:
            # 捩り分散に必要なボーン群
            arm_bone_name = "{0}腕".format(direction)
            arm_twist_bone_name = "{0}腕捩".format(direction)
            elbow_bone_name = "{0}ひじ".format(direction)
            wrist_twist_bone_name = "{0}手捩".format(direction)
            wrist_bone_name = "{0}手首".format(direction)

            twist_target_bones = [arm_bone_name, arm_twist_bone_name, elbow_bone_name, wrist_twist_bone_name, wrist_bone_name]

            if set(twist_target_bones).issubset(data_set.rep_model.bones):
                # 先モデルにボーンが揃ってる場合、捩り分散

                # 各ボーンのローカル軸
                local_z_axis = MVector3D(0, 0, -1)
                arm_local_x_axis = data_set.rep_model.get_local_x_axis(arm_bone_name)
                arm_twist_local_x_axis = data_set.rep_model.get_local_x_axis(arm_twist_bone_name)
                elbow_local_x_axis = data_set.rep_model.get_local_x_axis(elbow_bone_name)
                elbow_local_y_axis = MVector3D.crossProduct(elbow_local_x_axis, local_z_axis).normalized()
                wrist_twist_local_x_axis = data_set.rep_model.get_local_x_axis(wrist_twist_bone_name)
                wrist_local_x_axis = data_set.rep_model.get_local_x_axis(wrist_bone_name)

                logger.test("%s: axis: %s", arm_bone_name, arm_local_x_axis)
                logger.test("%s: axis: %s", arm_twist_bone_name, arm_twist_local_x_axis)
                logger.test("%s: axis: %s", elbow_bone_name, elbow_local_x_axis)
                logger.test("%s: axis: %s", elbow_bone_name, elbow_local_y_axis)
                logger.test("%s: axis: %s", wrist_twist_bone_name, wrist_twist_local_x_axis)
                logger.test("%s: axis: %s", wrist_bone_name, wrist_local_x_axis)

                prev_sep_fno = 0
                fnos = data_set.motion.get_bone_fnos(arm_bone_name, arm_twist_bone_name, elbow_bone_name, wrist_twist_bone_name, wrist_bone_name)
                for fno_idx, fno in enumerate(fnos):
                    logger.test("f: %s -------------", fno)

                    # 各ボーンのbf（補間曲線リセットなし）
                    arm_bf = data_set.motion.calc_bf(arm_bone_name, fno)
                    arm_twist_bf = data_set.motion.calc_bf(arm_twist_bone_name, fno)
                    elbow_bf = data_set.motion.calc_bf(elbow_bone_name, fno)
                    wrist_twist_bf = data_set.motion.calc_bf(wrist_twist_bone_name, fno)
                    wrist_bf = data_set.motion.calc_bf(wrist_bone_name, fno)

                    # 回転をローカル軸で分離
                    arm_x_qq, arm_y_qq, arm_z_qq = MServiceUtils.separate_local_qq(fno, arm_bone_name, arm_bf.rotation, arm_local_x_axis)
                    elbow_x_qq, elbow_y_qq, elbow_z_qq = MServiceUtils.separate_local_qq(fno, elbow_bone_name, elbow_bf.rotation, elbow_local_x_axis)
                    wrist_x_qq, wrist_y_qq, wrist_z_qq = MServiceUtils.separate_local_qq(fno, wrist_bone_name, wrist_bf.rotation, wrist_local_x_axis)

                    logger.test("f: %s, %s: total: %s", fno, arm_bone_name, arm_bf.rotation.toEulerAngles())
                    logger.test("f: %s, %s: x: %s", fno, arm_bone_name, arm_x_qq.toEulerAngles())
                    logger.test("f: %s, %s: y: %s", fno, arm_bone_name, arm_y_qq.toEulerAngles())
                    logger.test("f: %s, %s: z: %s", fno, arm_bone_name, arm_z_qq.toEulerAngles())
                    # logger.test("f: %s, %s: yz: %s", fno, arm_bone_name, arm_yz_qq.toEulerAngles())
                    logger.test("f: %s, %s: total: %s", fno, elbow_bone_name, elbow_bf.rotation.toEulerAngles())
                    logger.test("f: %s, %s: x: %s", fno, elbow_bone_name, elbow_x_qq.toEulerAngles())
                    logger.test("f: %s, %s: y: %s", fno, elbow_bone_name, elbow_y_qq.toEulerAngles())
                    logger.test("f: %s, %s: z: %s", fno, elbow_bone_name, elbow_z_qq.toEulerAngles())
                    # logger.test("f: %s, %s: yz: %s", fno, elbow_bone_name, elbow_yz_qq.toEulerAngles())
                    logger.test("f: %s, %s: total: %s", fno, wrist_bone_name, wrist_bf.rotation.toEulerAngles())
                    logger.test("f: %s, %s: x: %s", fno, wrist_bone_name, wrist_x_qq.toEulerAngles())
                    logger.test("f: %s, %s: y: %s", fno, wrist_bone_name, wrist_y_qq.toEulerAngles())
                    logger.test("f: %s, %s: z: %s", fno, wrist_bone_name, wrist_z_qq.toEulerAngles())
                    # logger.test("f: %s, %s: yz: %s", fno, wrist_bone_name, wrist_yz_qq.toEulerAngles())

                    # 腕YZを腕に
                    arm_result_qq = arm_z_qq * arm_y_qq

                    # 腕Xを腕捻りに（くの字はズレる）
                    arm_twist_result_qq = MQuaternion.fromAxisAndQuarternion(arm_twist_local_x_axis, arm_x_qq)

                    # 通常はひじYZ回転をひじボーンの順回転として扱う
                    # FIXME 逆肘考慮
                    elbow_result_qq = MQuaternion.fromAxisAndQuarternion(elbow_local_y_axis, elbow_z_qq * elbow_y_qq)

                    # # ひじベクトルを腕捻りで帳尻合わせ（ここでだいたい整合するか近似する）
                    # arm_twist_result_qq *= MServiceUtils.delegate_qq(fno, arm_twist_bone_name, arm_twist_result_qq, arm_twist_local_x_axis, \
                    #                                                  elbow_bf.rotation, elbow_result_qq, elbow_local_x_axis)

                    # 手首YZ回転を手首に
                    wrist_result_qq = wrist_z_qq * wrist_y_qq

                    # ひじXを手捻りに
                    wrist_twist_result_qq = MQuaternion.fromAxisAndQuarternion(wrist_twist_local_x_axis, elbow_x_qq)

                    # 手首Xを手捻りに
                    wrist_twist_result_qq *= MQuaternion.fromAxisAndQuarternion(wrist_twist_local_x_axis, wrist_x_qq)

                    # # 手捩りで手首ベクトル帳尻合わせ（ここでだいたい整合するか近似する）
                    # wrist_twist_result_qq *= MServiceUtils.delegate_qq(fno, wrist_twist_bone_name, wrist_twist_result_qq, wrist_twist_local_x_axis, \
                    #                                                    wrist_bf.rotation, wrist_result_qq, wrist_local_x_axis)

                    # 生成された回転量を保持
                    arm_bf.rotation = arm_result_qq
                    arm_twist_bf.rotation = arm_twist_result_qq
                    elbow_bf.rotation = elbow_result_qq
                    wrist_twist_bf.rotation = wrist_twist_result_qq
                    wrist_bf.rotation = wrist_result_qq

                    # 全部登録
                    data_set.motion.regist_bf(arm_bf, arm_bone_name, fno)
                    data_set.motion.regist_bf(arm_twist_bf, arm_twist_bone_name, fno)
                    data_set.motion.regist_bf(elbow_bf, elbow_bone_name, fno)
                    data_set.motion.regist_bf(wrist_twist_bf, wrist_twist_bone_name, fno)
                    data_set.motion.regist_bf(wrist_bf, wrist_bone_name, fno)

                    if fno // 500 > prev_sep_fno:
                        logger.info("-- %sフレーム目完了(%s手)", fno, direction)
                        prev_sep_fno = fno // 500

                logger.info("%s手捩り分散完了", direction)

    # つま先補正
    def adjust_toe_stance(self, data_set_idx: int, data_set: MOptionsDataSet):
        logger.info("つま先補正　【No.%s】", (data_set_idx + 1), decoration=MLogger.DECORATION_LINE)

        for direction in ["左", "右"]:
            # つま先調整に必要なボーン群
            toe_target_bones = ["{0}足ＩＫ".format(direction), "{0}つま先ＩＫ".format(direction), "{0}足首".format(direction), "{0}つま先実体".format(direction), "{0}足底実体".format(direction)]

            if set(toe_target_bones).issubset(data_set.org_model.bones) and set(toe_target_bones).issubset(data_set.rep_model.bones):
                org_toe_links = data_set.org_model.create_link_2_top_one("{0}つま先実体".format(direction))
                rep_toe_links = data_set.rep_model.create_link_2_top_one("{0}つま先実体".format(direction))

                if direction == "左":
                    logger.debug("元：左つま先：%s", data_set.org_model.left_toe_vertex)
                    logger.debug("先：左つま先：%s", data_set.rep_model.left_toe_vertex)
                else:
                    logger.debug("元：右つま先：%s", data_set.org_model.right_toe_vertex)
                    logger.debug("先：右つま先：%s", data_set.rep_model.right_toe_vertex)

                org_toe_limit = data_set.org_model.bones["{0}足首".format(direction)].position.distanceToPoint(data_set.org_model.bones["{0}つま先実体".format(direction)].position)
                rep_toe_limit = data_set.rep_model.bones["{0}足首".format(direction)].position.distanceToPoint(data_set.rep_model.bones["{0}つま先実体".format(direction)].position)

                toe_limit_ratio = rep_toe_limit / org_toe_limit

                logger.info("%sつま先補正", direction)
            
                prev_sep_fno = 0
                # 足ＩＫと足IK親の両方でフレーム番号をチェックする
                fnos = data_set.motion.get_bone_fnos("{0}足ＩＫ".format(direction), "{0}足IK親".format(direction))
                for fno_idx, fno in enumerate(fnos):
                    # 足ＩＫのbf(この時点では登録するか分からないので、補間曲線リセットなし)
                    ik_bf = data_set.motion.calc_bf("{0}足ＩＫ".format(direction), fno)

                    # 登録可否
                    is_ik_resist = False

                    # つま先の差異
                    org_toe_pos, toe_diff = self.get_toe_diff(data_set_idx, data_set, org_toe_links, rep_toe_links, toe_limit_ratio, "{0}足ＩＫ".format(direction), fno)

                    if org_toe_pos.y() > -org_toe_limit:
                        # つま先が足の甲の長さより大きい場合のみ調整

                        if org_toe_pos.y() < org_toe_limit and toe_diff != 0 and ik_bf.position.y() != 0:
                            # 足ＩＫを合わせる
                            adjust_toe_y = ik_bf.position.y() - toe_diff
                            ik_bf.position.setY(adjust_toe_y)
                            logger.debug("f: %s, %sつま先元補正: %s", fno, direction, adjust_toe_y)
                            # 登録対象
                            is_ik_resist = True
                        else:
                            logger.debug("f: %s, %sつま先元補正なし: %s", fno, direction, toe_diff)

                        # つま先を取り直す
                        rep_toe_pos, rep_sole_pos = self.get_toe_entity(data_set_idx, data_set, data_set.rep_model, data_set.motion, rep_toe_links, "{0}足ＩＫ".format(direction), fno)

                        # つま先と足底の地面に近い方を近づける
                        if rep_sole_pos.y() < rep_toe_pos.y() and rep_sole_pos.y() < data_set.rep_model.bones["{0}足底実体".format(direction)].position.y() and ik_bf.position.y() != 0:
                            # つま先が曲がっていて、足底の方が床に近い場合
                            adjust_toe_y = ik_bf.position.y() - rep_sole_pos.y()
                            # 登録対象
                            ik_bf.position.setY(adjust_toe_y)
                            is_ik_resist = True
                            logger.debug("f: %s, %sつま先床補正: 足底合わせ つま先実体: %s, 足底実体: %s, 足IK: %s", ik_bf.fno, direction, rep_toe_pos.y(), rep_sole_pos.y(), adjust_toe_y)
                        elif rep_toe_pos.y() < data_set.rep_model.bones["{0}つま先実体".format(direction)].position.y():
                            # つま先が伸びていて、足底よりも床に近い場合
                            adjust_toe_y = ik_bf.position.y() - rep_toe_pos.y()
                            # 登録対象
                            ik_bf.position.setY(adjust_toe_y)
                            is_ik_resist = True
                            logger.debug("f: %s, %sつま先床補正: つま先合わせ つま先実体: %s, 足底実体: %s, 足IK: %s", ik_bf.fno, direction, rep_toe_pos.y(), rep_sole_pos.y(), adjust_toe_y)
                        else:
                            logger.debug("f: %s, %sつま先床補正なし: つま先実体: %s, 足底実体: %s", ik_bf.fno, direction, rep_toe_pos.y(), rep_sole_pos.y())

                        # 登録対象である場合、それぞれのbfを登録
                        if is_ik_resist:
                            data_set.motion.regist_bf(ik_bf, "{0}足ＩＫ".format(direction), fno)
                    
                    if fno // 500 > prev_sep_fno:
                        logger.info("-- %sフレーム目完了", fno)
                        prev_sep_fno = fno // 500

                logger.info("%sつま先補正完了", direction)

    # つま先の差異
    def get_toe_diff(self, data_set_idx: int, data_set: MOptionsDataSet, org_toe_links: BoneLinks, rep_toe_links: BoneLinks, toe_limit_ratio: float, ik_bone_name: str, fno: int):
        org_toe_pos, org_sole_pos = self.get_toe_entity(data_set_idx, data_set, data_set.org_model, data_set.org_motion, org_toe_links, ik_bone_name, fno)
        rep_toe_pos, rep_sole_pos = self.get_toe_entity(data_set_idx, data_set, data_set.rep_model, data_set.motion, rep_toe_links, ik_bone_name, fno)
        
        logger.test("f: %s, %s - 作成元つま先: %s", fno, ik_bone_name[0], org_toe_pos)
        logger.test("f: %s, %s - 変換先つま先: %s", fno, ik_bone_name[0], rep_toe_pos)
        
        logger.test("f: %s, %s - 作成元足底: %s", fno, ik_bone_name[0], org_sole_pos)
        logger.test("f: %s, %s - 変換先足底: %s", fno, ik_bone_name[0], rep_sole_pos)
        
        # つま先が元モデルの上にある場合、つま先を合わせて下に下ろす（実体を考慮する）
        toe_diff = (rep_toe_pos.y() - data_set.rep_model.bones["{0}つま先実体".format(ik_bone_name[0])].position.y()) \
            - ((org_toe_pos.y() - data_set.org_model.bones["{0}つま先実体".format(ik_bone_name[0])].position.y()) * toe_limit_ratio) \
            + (data_set.rep_model.bones["{0}つま先実体".format(ik_bone_name[0])].position.y() - data_set.org_model.bones["{0}つま先実体".format(ik_bone_name[0])].position.y())
        logger.test("f: %s, %s - toe_diff: %s", fno, ik_bone_name[0], toe_diff)
        
        # 足底が元モデルの上にある場合、足底を合わせて下に下ろす（実体を考慮する）
        sole_diff = (rep_sole_pos.y() - data_set.rep_model.bones["{0}足底実体".format(ik_bone_name[0])].position.y()) \
            - ((org_sole_pos.y() - data_set.org_model.bones["{0}足底実体".format(ik_bone_name[0])].position.y()) * toe_limit_ratio) \
            + (data_set.rep_model.bones["{0}足底実体".format(ik_bone_name[0])].position.y() - data_set.org_model.bones["{0}足底実体".format(ik_bone_name[0])].position.y())
        logger.test("f: %s, %s - sole_diff: %s", fno, ik_bone_name[0], sole_diff)

        if rep_toe_pos.y() < rep_sole_pos.y():
            # つま先の方が床に近い場合
            return org_toe_pos, toe_diff

        # 足底の方が床に近い場合、足底合わせ
        return org_sole_pos, sole_diff
    
    # つま先実体のグローバル位置を取得する
    def get_toe_entity(self, data_set_idx: int, data_set: MOptionsDataSet, model: PmxModel, motion: VmdMotion, toe_links: BoneLinks, ik_bone_name: str, fno: int):
        toe_3ds = MServiceUtils.calc_global_pos(model, toe_links, motion, fno)

        logger.test(model.name)
        [logger.test("-- %s: %s", k, v) for k, v in toe_3ds.items()]

        toe_pos = toe_3ds["{0}つま先実体".format(ik_bone_name[0])]
        sole_pos = toe_3ds["{0}足底実体".format(ik_bone_name[0])]

        return toe_pos, sole_pos

    # センタースタンス補正
    def adjust_center_stance(self, data_set_idx: int, data_set: MOptionsDataSet):
        logger.info("センタースタンス補正　【No.%s】", (data_set_idx + 1), decoration=MLogger.DECORATION_LINE)

        # センター調整に必要なボーン群
        center_target_bones = ["センター", "上半身", "下半身", "左足ＩＫ", "右足ＩＫ", "左足", "右足"]

        if set(center_target_bones).issubset(data_set.org_model.bones) and set(center_target_bones).issubset(data_set.rep_model.bones) and "センター" in data_set.motion.bones:
            # 判定用のセンターボーン名（グルーブがある場合、グルーブまでを対象とする）
            org_center_bone_name = "グルーブ" if "グルーブ" in data_set.org_model.bones else "センター"
            rep_center_bone_name = "グルーブ" if "グルーブ" in data_set.rep_model.bones else "センター"

            # 元モデルのリンク生成
            org_center_links = data_set.org_model.create_link_2_top_one(org_center_bone_name)
            org_leg_ik_links = data_set.org_model.create_link_2_top_lr("足ＩＫ")
            org_upper_links = data_set.org_model.create_link_2_top_one("上半身")
            org_lower_links = data_set.org_model.create_link_2_top_one("下半身")
            org_leg_links = data_set.org_model.create_link_2_top_lr("足")

            # 変換先モデルのリンク生成
            rep_center_links = data_set.rep_model.create_link_2_top_one(rep_center_bone_name)
            rep_leg_ik_links = data_set.rep_model.create_link_2_top_lr("足ＩＫ")
            rep_upper_links = data_set.rep_model.create_link_2_top_one("上半身")
            rep_lower_links = data_set.rep_model.create_link_2_top_one("下半身")
            rep_leg_links = data_set.rep_model.create_link_2_top_lr("足")

            # 準備（細分化）
            self.prepare_split_stance(data_set_idx, data_set, "センター")

            logger.info("センタースタンス補正: 準備終了")

            prev_fno = 0
            for fno in data_set.motion.get_bone_fnos("センター"):
                bf = data_set.motion.bones["センター"][fno]
                if bf.key:
                    logger.debug("f: %s, 調整前: %s", bf.fno, bf.position)
                    bf.position += self.calc_center_offset_by_leg_ik(bf, data_set_idx, data_set, \
                                                                     org_center_links, org_leg_ik_links, rep_center_links, rep_leg_ik_links, \
                                                                     org_center_bone_name, rep_center_bone_name)
                    logger.debug("f: %s, 足IKオフセット後: %s", bf.fno, bf.position)
                    bf.position += self.calc_center_offset_by_trunk(bf, data_set_idx, data_set, \
                                                                    org_center_links, org_upper_links, org_lower_links, org_leg_links, \
                                                                    rep_center_links, rep_upper_links, rep_lower_links, rep_leg_links, \
                                                                    org_center_bone_name, rep_center_bone_name)
                    logger.debug("f: %s, 体幹オフセット後: %s", bf.fno, bf.position)

                if fno // 500 > prev_fno:
                    logger.info("-- %sフレーム目完了", fno)
                    prev_fno = fno // 500

            logger.info("センタースタンス補正: 終了")

    # 足IKによるセンターオフセット値
    def calc_center_offset_by_leg_ik(self, bf: VmdBoneFrame, data_set_idx: int, data_set: MOptionsDataSet, \
                                     org_center_links: BoneLinks, org_leg_ik_links: BoneLinks, \
                                     rep_center_links: BoneLinks, rep_leg_ik_links: BoneLinks, \
                                     org_center_bone_name: str, rep_center_bone_name: str):

        # 元モデルのセンターオフセット
        org_front_center_ik_offset, org_center_direction_qq = \
            self.calc_center_offset_by_leg_ik_model(bf, data_set_idx, data_set, data_set.org_model, data_set.org_motion, \
                                                    org_center_links, org_leg_ik_links, org_center_bone_name)
        logger.test("f: %s, org_front_center_ik_offset: %s", bf.fno, org_front_center_ik_offset)

        # 先モデルのセンターオフセット
        rep_front_center_ik_offset, rep_center_direction_qq = \
            self.calc_center_offset_by_leg_ik_model(bf, data_set_idx, data_set, data_set.rep_model, data_set.motion, \
                                                    rep_center_links, rep_leg_ik_links, rep_center_bone_name)
        logger.test("f: %s, rep_front_center_ik_offset: %s", bf.fno, rep_front_center_ik_offset)
        
        # 元モデルに本来のXZ比率をかけて、それと先モデルの差をオフセットとする
        front_center_ik_offset = rep_front_center_ik_offset - (org_front_center_ik_offset * data_set.original_xz_ratio)
        logger.debug("f: %s, front_center_ik_offset: %s", bf.fno, front_center_ik_offset)

        # 回転を元に戻した位置
        rotated_center_3ds = MServiceUtils.calc_global_pos_by_direction(rep_center_direction_qq, {rep_center_bone_name: front_center_ik_offset})

        return rotated_center_3ds[rep_center_bone_name]

    # モデル別足IKによるセンターオフセット値
    def calc_center_offset_by_leg_ik_model(self, bf: VmdBoneFrame, data_set_idx: int, data_set: MOptionsDataSet, \
                                           model: PmxModel, motion: VmdMotion, \
                                           center_links: BoneLinks, leg_ik_links: BoneLinks, center_bone_name: str):

        # センターまでの位置
        center_global_3ds, front_center_global_3ds, center_direction_qq = \
            MServiceUtils.calc_front_global_pos(model, center_links, motion, bf.fno)

        # 左足IKまでの位置
        left_leg_ik_global_3ds, front_left_leg_ik_global_3ds, left_leg_ik_direction_qq = \
            MServiceUtils.calc_front_global_pos(model, leg_ik_links["左"], motion, bf.fno)

        # 右足IKまでの位置
        right_leg_ik_global_3ds, front_right_leg_ik_global_3ds, right_leg_ik_direction_qq = \
            MServiceUtils.calc_front_global_pos(model, leg_ik_links["右"], motion, bf.fno)
        
        front_center_pos = front_center_global_3ds[center_bone_name]
        front_left_ik_pos = front_left_leg_ik_global_3ds["左足ＩＫ"]
        front_right_ik_pos = front_right_leg_ik_global_3ds["右足ＩＫ"]

        # 足IKの中間とセンターの差分をオフセットとする
        front_center_ik_offset = ((front_left_ik_pos + front_right_ik_pos) / 2 - front_center_pos)
        front_center_ik_offset.effective()
        front_center_ik_offset.setY(0)

        return front_center_ik_offset, center_direction_qq

    # 体幹によるセンターオフセット値
    def calc_center_offset_by_trunk(self, bf: VmdBoneFrame, data_set_idx: int, data_set: MOptionsDataSet, \
                                    org_center_links: BoneLinks, org_upper_links: BoneLinks, org_lower_links: BoneLinks, org_leg_links: BoneLinks, \
                                    rep_center_links: BoneLinks, rep_upper_links: BoneLinks, rep_lower_links: BoneLinks, rep_leg_links: BoneLinks, \
                                    org_center_bone_name: str, rep_center_bone_name: str):
        
        # 元モデルのセンター差分
        org_front_upper_center_diff, org_front_lower_center_diff, org_upper_direction_qq, org_lower_direction_qq = \
            self.calc_center_offset_by_trunk_model(bf, data_set_idx, data_set, data_set.org_model, data_set.org_motion, \
                                                   org_center_links, org_upper_links, org_lower_links, org_center_bone_name)
    
        # 先モデルのセンター差分
        rep_front_upper_center_diff, rep_front_lower_center_diff, rep_upper_direction_qq, rep_lower_direction_qq = \
            self.calc_center_offset_by_trunk_model(bf, data_set_idx, data_set, data_set.rep_model, data_set.motion, \
                                                   rep_center_links, rep_upper_links, rep_lower_links, rep_center_bone_name)
    
        # 上半身差分
        front_upper_center_diff = rep_front_upper_center_diff - (org_front_upper_center_diff * data_set.original_xz_ratio)
        logger.debug("f: %s, front_upper_center_diff: %s", bf.fno, front_upper_center_diff)
    
        # 下半身差分
        front_lower_center_diff = rep_front_lower_center_diff - (org_front_lower_center_diff * data_set.original_xz_ratio)
        logger.debug("f: %s, front_lower_center_diff: %s", bf.fno, front_lower_center_diff)

        # 元々の方向に向かせる
        rotated_upper_center_3ds = MServiceUtils.calc_global_pos_by_direction(rep_upper_direction_qq, {rep_center_bone_name: front_upper_center_diff})
        rotated_lower_center_3ds = MServiceUtils.calc_global_pos_by_direction(rep_lower_direction_qq, {rep_center_bone_name: front_lower_center_diff})

        # 差分の平均
        center_trunk_diff = (rotated_upper_center_3ds[rep_center_bone_name] + rotated_lower_center_3ds[rep_center_bone_name]) / 2
        center_trunk_diff.effective()
        center_trunk_diff.setY(0)
        logger.debug("f: %s, center_trunk_diff: %s", bf.fno, center_trunk_diff)

        return center_trunk_diff

    def calc_center_offset_by_trunk_model(self, bf: VmdBoneFrame, data_set_idx: int, data_set: MOptionsDataSet, \
                                          model: PmxModel, motion: VmdMotion, \
                                          center_links: BoneLinks, upper_links: BoneLinks, lower_links: BoneLinks, \
                                          center_bone_name: str):

        # センターまでの位置
        center_global_3ds, front_center_global_3ds, center_direction_qq = \
            MServiceUtils.calc_front_global_pos(model, center_links, motion, bf.fno)
        
        # 上半身を原点として回った場合のモーション
        upper_motion = VmdMotion()
        for lidx, lname in enumerate(upper_links.all().keys()):
            calc_bf = copy.deepcopy(motion.calc_bf(lname, bf.fno))
            
            if lidx == 0:
                # SIZING_ROOTに上半身とセンターとのズレを加算する
                calc_bf.position += (model.bones["上半身"].position - model.bones["センター"].position)
                calc_bf.position.setY(0)
            
            upper_motion.bones[lname] = {bf.fno: calc_bf}

        # 上半身までの位置(センターを含む)
        upper_global_3ds, front_upper_global_3ds, upper_direction_qq = \
            MServiceUtils.calc_front_global_pos(model, upper_links, upper_motion, bf.fno)

        # 上半身起点に基づくセンター差分
        front_upper_center_diff = front_center_global_3ds[center_bone_name] - front_upper_global_3ds[center_bone_name]

        # ---------------
        
        # 下半身を原点として回った場合のモーション
        lower_motion = VmdMotion()
        for lidx, lname in enumerate(lower_links.all().keys()):
            calc_bf = copy.deepcopy(motion.calc_bf(lname, bf.fno))
            
            if lidx == 0:
                # SIZING_ROOTに下半身とセンターとのズレを加算する
                calc_bf.position += (model.bones["下半身"].position - model.bones["センター"].position)
                calc_bf.position.setY(0)
            
            lower_motion.bones[lname] = {bf.fno: calc_bf}

        # 下半身までの位置(センターを含む)
        lower_global_3ds, front_lower_global_3ds, lower_direction_qq = \
            MServiceUtils.calc_front_global_pos(model, lower_links, lower_motion, bf.fno)

        # 下半身起点に基づくセンター差分
        front_lower_center_diff = front_center_global_3ds[center_bone_name] - front_lower_global_3ds[center_bone_name]

        return front_upper_center_diff, front_lower_center_diff, upper_direction_qq, lower_direction_qq

    # 上半身スタンス補正
    def adjust_upper_stance(self, data_set_idx: int, data_set: MOptionsDataSet):
        logger.info("上半身スタンス補正　【No.%s】", (data_set_idx + 1), decoration=MLogger.DECORATION_LINE)

        # 上半身調整に必要なボーン群
        upper_target_bones = ["上半身", "頭", "首", "左腕", "右腕"]

        # 上半身2調整に必要なボーン群
        upper2_target_bones = ["上半身", "上半身2", "頭", "首", "左腕", "右腕"]

        # モデルとモーション全部に上半身2がある場合、TRUE
        is_upper2_existed = set(upper2_target_bones).issubset(data_set.org_model.bones) and set(upper2_target_bones).issubset(data_set.rep_model.bones) \
            and "上半身2" in data_set.motion.bones and len(data_set.motion.bones["上半身2"]) > 1

        if set(upper_target_bones).issubset(data_set.org_model.bones) and set(upper_target_bones).issubset(data_set.rep_model.bones) and "上半身" in data_set.motion.bones:
            # 元モデルのリンク生成
            org_head_links = data_set.org_model.create_link_2_top_one("頭")
            org_upper_links = data_set.org_model.create_link_2_top_one("上半身")
            org_arm_links = data_set.org_model.create_link_2_top_lr("腕")

            # 変換先モデルのリンク生成
            rep_head_links = data_set.rep_model.create_link_2_top_one("頭")
            rep_upper_links = data_set.rep_model.create_link_2_top_one("上半身")
            rep_arm_links = data_set.rep_model.create_link_2_top_lr("腕")

            # 元モデルの上半身の傾き
            org_upper_slope = (data_set.org_model.bones["頭"].position - data_set.org_model.bones["上半身"].position).normalized()

            # 上半身からTO_BONEへの傾き
            rep_upper_slope = (data_set.rep_model.bones["頭"].position - data_set.rep_model.bones["上半身"].position).normalized()
            rep_upper_slope_up = MVector3D(-1, 0, 0)
            rep_upper_slope_cross = MVector3D.crossProduct(rep_upper_slope, rep_upper_slope_up).normalized()
            
            logger.test("上半身 slope: %s", rep_upper_slope)
            logger.test("上半身 cross: %s", rep_upper_slope_cross)

            # 上半身の傾き度合い - 0.1 を変化量の上限とする
            dot_limit = MVector3D.dotProduct(org_upper_slope.normalized(), rep_upper_slope.normalized()) - 0.1
            logger.debug("dot_limit: %s", dot_limit)

            # 初期傾き
            rep_upper_initial_slope_qq = MQuaternion.fromDirection(rep_upper_slope, rep_upper_slope_cross)

            # 初期状態の上半身2の傾き
            initial_bf = VmdBoneFrame(fno=0, name="上半身")
            initial_dataset = MOptionsDataSet(VmdMotion(), data_set.org_model, data_set.rep_model, data_set.output_vmd_path, data_set.substitute_model_flg, data_set.twist_flg)

            self.calc_rotation_stance(initial_bf, data_set_idx, initial_dataset, \
                                      org_upper_links, org_upper_links, org_head_links, org_head_links, org_arm_links, \
                                      rep_upper_links, rep_upper_links, rep_head_links, rep_head_links, rep_arm_links, \
                                      "上半身", "上半身", "頭", rep_upper_links.get("上半身", offset=-1).name, \
                                      rep_upper_initial_slope_qq, MQuaternion(), self.def_calc_up_upper, 0)

            # 内積
            dot = MVector3D.dotProduct(org_upper_slope.normalized(), rep_upper_slope.normalized())

            if dot >= 0.8:
                upper_initial_qq = initial_bf.rotation
                # 肩の傾き度合い - 0.1 を変化量の上限とする
                dot_limit = dot - 0.1
            else:
                # 初期姿勢が違いすぎてる場合、初期姿勢を維持しない（四つ足等）
                upper_initial_qq = MQuaternion()
                dot_limit = 0

            logger.debug("dot: %s", dot)
            logger.debug("upper_initial_qq: %s", upper_initial_qq)
            logger.debug("dot_limit: %s", dot_limit)

            # 準備（細分化）
            self.prepare_split_stance(data_set_idx, data_set, "上半身")

            logger.info("上半身スタンス補正: 準備終了")

            prev_fno = 0
            for fno in data_set.motion.get_bone_fnos("上半身"):
                bf = data_set.motion.bones["上半身"][fno]
                if bf.key:
                    self.calc_rotation_stance(bf, data_set_idx, data_set, \
                                              org_upper_links, org_upper_links, org_head_links, org_head_links, org_arm_links, \
                                              rep_upper_links, rep_upper_links, rep_head_links, rep_head_links, rep_arm_links, \
                                              "上半身", "上半身", "頭", rep_upper_links.get("上半身", offset=-1).name, \
                                              rep_upper_initial_slope_qq, upper_initial_qq, self.def_calc_up_upper, dot_limit)
                if fno // 500 > prev_fno:
                    logger.info("-- %sフレーム目完了", fno)
                    prev_fno = fno // 500

            # 子の角度調整
            self.adjust_rotation_by_parent(data_set_idx, data_set, "首", "上半身")
            self.adjust_rotation_by_parent(data_set_idx, data_set, "左腕", "上半身")
            self.adjust_rotation_by_parent(data_set_idx, data_set, "右腕", "上半身")

            logger.info("上半身スタンス補正: 終了")

            if is_upper2_existed:
                # 上半身2がある場合
                # 元モデルのリンク生成
                org_head_links = data_set.org_model.create_link_2_top_one("頭")
                org_upper2_links = data_set.org_model.create_link_2_top_one("上半身2")

                # 変換先モデルのリンク生成
                rep_head_links = data_set.rep_model.create_link_2_top_one("頭")
                rep_upper2_links = data_set.rep_model.create_link_2_top_one("上半身2")

                # 元モデルの上半身2の傾き
                org_upper2_slope = (data_set.org_model.bones["頭"].position - data_set.org_model.bones["上半身2"].position).normalized()

                # 上半身からTO_BONEへの傾き
                rep_upper2_slope = (data_set.rep_model.bones["頭"].position - data_set.rep_model.bones["上半身2"].position).normalized()
                rep_upper2_slope_up = MVector3D(-1, 0, 0)
                rep_upper2_slope_cross = MVector3D.crossProduct(rep_upper2_slope, rep_upper2_slope_up).normalized()
                
                logger.test("上半身 slope: %s", rep_upper2_slope)
                logger.test("上半身 cross: %s", rep_upper2_slope_cross)

                rep_upper2_initial_slope_qq = MQuaternion.fromDirection(rep_upper2_slope, rep_upper2_slope_cross)

                # 初期状態の上半身2の傾き
                initial_bf = VmdBoneFrame(fno=0, name="上半身2")
                initial_dataset = MOptionsDataSet(VmdMotion(), data_set.org_model, data_set.rep_model, data_set.output_vmd_path, data_set.substitute_model_flg, data_set.twist_flg)

                self.calc_rotation_stance(initial_bf, data_set_idx, initial_dataset, \
                                          org_upper2_links, org_upper2_links, org_head_links, org_head_links, org_arm_links, \
                                          rep_upper2_links, rep_upper2_links, rep_head_links, rep_head_links, rep_arm_links, \
                                          "上半身2", "上半身2", "頭", rep_upper2_links.get("上半身2", offset=-1).name, \
                                          rep_upper2_initial_slope_qq, MQuaternion(), self.def_calc_up_upper, 0)

                # 内積
                dot = MVector3D.dotProduct(org_upper2_slope.normalized(), rep_upper2_slope.normalized())

                if dot >= 0.8:
                    upper2_initial_qq = initial_bf.rotation
                    # 肩の傾き度合い - 0.1 を変化量の上限とする
                    dot2_limit = dot - 0.1
                else:
                    # 初期姿勢が違いすぎてる場合、初期姿勢を維持しない（四つ足等）
                    upper2_initial_qq = MQuaternion()
                    dot2_limit = 0

                logger.debug("dot: %s", dot)
                logger.debug("upper2_initial_qq: %s", upper2_initial_qq)
                logger.debug("dot2_limit: %s", dot2_limit)

                # 準備（細分化）
                self.prepare_split_stance(data_set_idx, data_set, "上半身2")

                logger.info("上半身2スタンス補正: 準備終了")

                prev_fno = 0
                for fno in data_set.motion.get_bone_fnos("上半身2"):
                    bf = data_set.motion.bones["上半身2"][fno]
                    if bf.key:
                        self.calc_rotation_stance(bf, data_set_idx, data_set, \
                                                  org_upper2_links, org_upper2_links, org_head_links, org_head_links, org_arm_links, \
                                                  rep_upper2_links, rep_upper2_links, rep_head_links, rep_head_links, rep_arm_links, \
                                                  "上半身2", "上半身2", "頭", rep_upper2_links.get("上半身2", offset=-1).name, \
                                                  rep_upper2_initial_slope_qq, upper2_initial_qq, self.def_calc_up_upper, dot2_limit)

                    if fno // 500 > prev_fno:
                        logger.info("-- %sフレーム目完了", fno)
                        prev_fno = fno // 500

                # 子の角度調整
                self.adjust_rotation_by_parent(data_set_idx, data_set, "首", "上半身2")
                self.adjust_rotation_by_parent(data_set_idx, data_set, "左腕", "上半身2")
                self.adjust_rotation_by_parent(data_set_idx, data_set, "右腕", "上半身2")

                logger.info("上半身2スタンス補正: 終了")

    # 肩スタンス補正
    def adjust_shoulder_stance(self, data_set_idx: int, data_set: MOptionsDataSet):
        logger.info("肩スタンス補正　【No.%s】", (data_set_idx + 1), decoration=MLogger.DECORATION_LINE)

        for shoulder_p_name, shoulder_name, arm_name in [("右肩P", "右肩", "右腕"), ("左肩P", "左肩", "左腕")]:
            # 肩調整に必要なボーン群(肩Pは含めない)
            shoulder_target_bones = ["頭", "首", "首根元", shoulder_name, arm_name, "{0}下延長".format(arm_name), "上半身"]

            if set(shoulder_target_bones).issubset(data_set.org_model.bones) and set(shoulder_target_bones).issubset(data_set.rep_model.bones) and shoulder_name in data_set.motion.bones:
                # 肩Pを使うかどうか
                is_shoulder_p = True if shoulder_p_name in data_set.motion.bones and shoulder_p_name in data_set.rep_model.bones and shoulder_p_name in data_set.org_model.bones else False

                # 元モデルのリンク生成
                org_neck_base_links = data_set.org_model.create_link_2_top_one("首根元")
                org_shoulder_links = data_set.org_model.create_link_2_top_one(shoulder_name)
                # org_shoulder_p_links = None if not is_shoulder_p else data_set.org_model.create_link_2_top_one(shoulder_p_name)
                org_arm_links = data_set.org_model.create_link_2_top_lr("腕")
                org_arm_under_links = data_set.org_model.create_link_2_top_one("{0}下延長".format(arm_name))

                # 変換先モデルのリンク生成
                rep_neck_base_links = data_set.rep_model.create_link_2_top_one("首根元")
                rep_shoulder_links = data_set.rep_model.create_link_2_top_one(shoulder_name)
                # rep_shoulder_p_links = None if not is_shoulder_p else data_set.rep_model.create_link_2_top_one(shoulder_p_name)
                rep_arm_links = data_set.rep_model.create_link_2_top_lr("腕")
                rep_arm_under_links = data_set.rep_model.create_link_2_top_one("{0}下延長".format(arm_name))

                logger.test("%s: %s", arm_name, data_set.org_model.bones[arm_name].position)
                logger.test("%s: %s", shoulder_name, data_set.org_model.bones[shoulder_name].position)
                logger.test("首根元: %s", data_set.org_model.bones["首根元"].position)

                # 元モデルの肩の傾き
                org_shoulder_slope = (data_set.org_model.bones[arm_name].position - data_set.org_model.bones[shoulder_name].position).normalized()

                # 肩から腕への傾き
                rep_shoulder_slope = (data_set.rep_model.bones[arm_name].position - data_set.rep_model.bones[shoulder_name].position).normalized()
                
                rep_shoulder_slope_up = MVector3D(1, -1, 0)
                rep_shoulder_slope_cross = MVector3D.crossProduct(rep_shoulder_slope, rep_shoulder_slope_up).normalized()
                
                rep_shoulder_initial_slope_qq = MQuaternion.fromDirection(rep_shoulder_slope, rep_shoulder_slope_cross)

                logger.test("肩 slope: %s", rep_shoulder_slope)
                logger.test("肩 cross: %s", rep_shoulder_slope_cross)

                # 初期状態の肩の傾き
                initial_bf = VmdBoneFrame(fno=0, name=shoulder_name)
                initial_dataset = MOptionsDataSet(VmdMotion(), data_set.org_model, data_set.rep_model, data_set.output_vmd_path, data_set.substitute_model_flg, data_set.twist_flg)

                self.calc_rotation_stance(initial_bf, data_set_idx, initial_dataset, \
                                          org_neck_base_links, org_shoulder_links, org_arm_links[shoulder_name[0]], org_arm_under_links, org_arm_links, \
                                          rep_neck_base_links, rep_shoulder_links, rep_arm_links[shoulder_name[0]], rep_arm_under_links, rep_arm_links, \
                                          "首根元", shoulder_name, arm_name, rep_shoulder_links.get(shoulder_name, offset=-1).name, \
                                          rep_shoulder_initial_slope_qq, MQuaternion(), self.def_calc_up_shoulder, 0)
                
                # 内積
                dot = MVector3D.dotProduct(org_shoulder_slope.normalized(), rep_shoulder_slope.normalized())

                if dot >= 0.7:
                    shoulder_initial_qq = initial_bf.rotation
                    # 肩の傾き度合い ＋α を変化量の上限とする
                    dot_limit = dot - 0.1
                else:
                    # 初期姿勢が違いすぎてる場合、初期姿勢を維持しない（四つ足等）
                    shoulder_initial_qq = MQuaternion()
                    dot_limit = 0

                logger.debug("dot: %s", dot)
                logger.debug("shoulder_initial_qq: %s", shoulder_initial_qq)
                logger.debug("dot_limit: %s", dot_limit)

                # 準備（細分化）
                self.prepare_split_stance(data_set_idx, data_set, shoulder_name)

                if is_shoulder_p:
                    # 肩Pがある場合、肩Pも細分化
                    self.prepare_split_stance(data_set_idx, data_set, shoulder_p_name)

                logger.info("%sスタンス補正: 準備終了", shoulder_name)
                
                # # 肩と肩P一緒に調整する
                # prev_fno = 0
                # if is_shoulder_p:
                #     logger.info("%sスタンス補正", shoulder_p_name)

                #     for fno in data_set.motion.get_bone_fnos(shoulder_name, shoulder_p_name):
                #         # 肩Pがある場合
                #         shoulder_p_bf = data_set.motion.calc_bf(shoulder_p_name, fno)
                        
                #         self.calc_rotation_stance(shoulder_p_bf, data_set_idx, data_set, \
                #                                   org_neck_base_links, org_shoulder_p_links, org_arm_links[shoulder_p_name[0]], org_arm_under_links, org_arm_links, \
                #                                   rep_neck_base_links, rep_shoulder_p_links, rep_arm_links[shoulder_p_name[0]], rep_arm_under_links, rep_arm_links, \
                #                                   "首根元", shoulder_p_name, arm_name, rep_shoulder_p_links.get(shoulder_p_name, offset=-1).name, \
                #                                   rep_shoulder_initial_slope_qq, shoulder_initial_qq, self.def_calc_up_shoulder, dot_limit)
                        
                #         # bf登録
                #         data_set.motion.regist_bf(shoulder_p_bf, shoulder_p_name, fno)

                #         if fno // 500 > prev_fno:
                #             logger.info("-- %sフレーム目完了", fno)
                #             prev_fno = fno // 500
                    
                #     self.adjust_rotation_by_parent(data_set_idx, data_set, arm_name, shoulder_p_name)

                # logger.info("%sスタンス補正: 終了", shoulder_p_name)
                
                logger.info("%sスタンス補正", shoulder_name)

                prev_fno = 0

                # 肩Pと肩の両方のキーフレリスト
                fnos = data_set.motion.get_bone_fnos(shoulder_name, shoulder_p_name)

                # 肩P除去
                del data_set.motion.bones[shoulder_p_name]

                # 子として肩の角度調整
                self.adjust_rotation_by_parent(data_set_idx, data_set, shoulder_name, shoulder_p_name)

                for fno in fnos:
                    # 肩補正
                    shoulder_bf = data_set.motion.calc_bf(shoulder_name, fno)

                    self.calc_rotation_stance(shoulder_bf, data_set_idx, data_set, \
                                              org_shoulder_links, org_shoulder_links, org_arm_links[shoulder_name[0]], org_arm_under_links, org_arm_links, \
                                              rep_shoulder_links, rep_shoulder_links, rep_arm_links[shoulder_name[0]], rep_arm_under_links, rep_arm_links, \
                                              shoulder_name, shoulder_name, arm_name, rep_shoulder_links.get(shoulder_name, offset=-1).name, \
                                              rep_shoulder_initial_slope_qq, shoulder_initial_qq, self.def_calc_up_shoulder, dot_limit)
                    
                    # bf登録
                    data_set.motion.regist_bf(shoulder_bf, shoulder_name, fno)
                        
                    if fno // 500 > prev_fno:
                        logger.info("-- %sフレーム目完了", fno)
                        prev_fno = fno // 500
                
                # 子の角度調整
                self.adjust_rotation_by_parent(data_set_idx, data_set, arm_name, shoulder_name)

                logger.info("%sスタンス補正: 終了", shoulder_name)

    # 指定したボーンを親ボーンの調整量に合わせてキャンセル
    def adjust_rotation_by_parent(self, data_set_idx: int, data_set: MOptionsDataSet, target_bone_name: str, target_parent_name: str):
        for fno in data_set.motion.get_bone_fnos(target_bone_name):
            bf = data_set.motion.bones[target_bone_name][fno]
            if bf.key:
                # 元々の親bf
                org_parent_bf = data_set.org_motion.calc_bf(target_parent_name, fno)
                # 調整後の親bf
                rep_parent_bf = data_set.motion.calc_bf(target_parent_name, fno)

                # 元々の親bfのdeformed回転量
                org_deformed_qq = MServiceUtils.deform_rotation(data_set.org_model, data_set.org_motion, org_parent_bf)
                # 調整後の親bfのdeformed回転量
                rep_deformed_qq = MServiceUtils.deform_rotation(data_set.rep_model, data_set.motion, rep_parent_bf)

                bf.rotation = rep_deformed_qq.inverted() * org_deformed_qq * bf.rotation

    # 定義: 傾きを求める方向の位置計算（上半身）
    def def_calc_up_upper(self, bf: VmdBoneFrame, data_set_idx: int, data_set: MOptionsDataSet, \
                          org_base_links: BoneLinks, org_from_links: BoneLinks, org_to_links: BoneLinks, org_head_links: BoneLinks, org_arm_links: BoneLinks, \
                          base_bone_name: str, from_bone_name: str, to_bone_name: str):
        # 左腕ボーンまでの位置
        org_left_arm_global_3ds = MServiceUtils.calc_global_pos(data_set.org_model, org_arm_links["左"], data_set.org_motion, bf.fno, org_from_links)
        org_left_arm_pos = org_left_arm_global_3ds["左腕"]
        logger.test("f: %s, org_left_arm_pos: %s", bf.fno, org_left_arm_pos)

        # 右腕ボーンまでの位置
        org_right_arm_global_3ds = MServiceUtils.calc_global_pos(data_set.org_model, org_arm_links["右"], data_set.org_motion, bf.fno, org_from_links)
        org_right_arm_pos = org_right_arm_global_3ds["右腕"]
        logger.test("f: %s, org_right_arm_pos: %s", bf.fno, org_right_arm_pos)
        
        return org_right_arm_pos - org_left_arm_pos

    # 定義: 傾きを求める方向の位置計算（肩）
    def def_calc_up_shoulder(self, bf: VmdBoneFrame, data_set_idx: int, data_set: MOptionsDataSet, \
                             org_base_links: BoneLinks, org_from_links: BoneLinks, org_to_links: BoneLinks, org_arm_under_links: BoneLinks, org_arm_links: BoneLinks, \
                             base_bone_name: str, from_bone_name: str, to_bone_name: str):
        # 腕下延長ボーンまでの位置
        org_arm_under_global_3ds = MServiceUtils.calc_global_pos(data_set.org_model, org_arm_under_links, data_set.org_motion, bf.fno, org_from_links)
        org_arm_under_pos = org_arm_under_global_3ds["{0}下延長".format(to_bone_name)]
        logger.test("f: %s, org_arm_under_pos: %s", bf.fno, org_arm_under_pos)

        # 腕ボーンまでの位置
        org_arm_global_3ds = MServiceUtils.calc_global_pos(data_set.org_model, org_arm_links[to_bone_name[0]], data_set.org_motion, bf.fno, org_from_links)
        org_arm_pos = org_arm_global_3ds[to_bone_name]
        logger.test("f: %s, org_arm_pos: %s", bf.fno, org_arm_pos)

        return org_arm_under_pos - org_arm_pos

    # スタンス補正
    def calc_rotation_stance(self, bf: VmdBoneFrame, data_set_idx: int, data_set: MOptionsDataSet, \
                             org_base_links: BoneLinks, org_from_links: BoneLinks, org_to_links: BoneLinks, org_head_links: BoneLinks, org_arm_links: BoneLinks, \
                             rep_base_links: BoneLinks, rep_from_links: BoneLinks, rep_to_links: BoneLinks, rep_head_links: BoneLinks, rep_arm_links: BoneLinks, \
                             base_bone_name: str, from_bone_name: str, to_bone_name: str, rep_parent_bone_name: str, \
                             rep_initial_slope_qq: MQuaternion, cancel_qq: MQuaternion, def_calc_up, dot_limit):
        logger.test("f: %s -----------------------------", bf.fno)

        # 基準より親の回転量
        parent_qq = MServiceUtils.calc_direction_qq(data_set.rep_model, rep_base_links.from_links(rep_parent_bone_name), data_set.motion, bf.fno)

        # -------------

        # TO位置の再計算
        new_rep_to_pos, rep_to_pos, rep_base_pos, rep_from_pos \
            = self.recalc_to_pos(bf, data_set_idx, data_set, \
                                 org_base_links, org_from_links, org_to_links, org_arm_links, \
                                 rep_base_links, rep_from_links, rep_to_links, rep_arm_links, \
                                 base_bone_name, from_bone_name, to_bone_name)

        # UP方向の再計算（元モデルで計算する）
        up_pos = def_calc_up(bf, data_set_idx, data_set, org_base_links, org_from_links, org_to_links, org_head_links, org_arm_links, \
                             base_bone_name, from_bone_name, to_bone_name)

        # ---------------
        # FROMの回転量を再計算する
        direction = new_rep_to_pos - rep_from_pos
        up = MVector3D.crossProduct(direction, up_pos)
        from_orientation = MQuaternion.fromDirection(direction.normalized(), up.normalized())
        initial = rep_initial_slope_qq
        from_rotation = parent_qq.inverted() * cancel_qq.inverted() * from_orientation * initial.inverted()
        from_rotation.normalize()
        logger.test("f: %s, rep_base_pos(%s): %s", bf.fno, base_bone_name, rep_base_pos)
        logger.test("f: %s, rep_from_pos(%s): %s", bf.fno, from_bone_name, rep_from_pos)
        logger.test("f: %s, rep_to_pos(%s): %s", bf.fno, to_bone_name, new_rep_to_pos)
        logger.test("f: %s, up_pos: %s", bf.fno, up_pos)
        logger.test("f: %s, direction(%s): %s", bf.fno, to_bone_name, direction)
        logger.test("f: %s, up: %s", bf.fno, up)
        logger.test("f: %s, parent(%s): %s", bf.fno, rep_parent_bone_name, parent_qq.toEulerAngles())
        logger.test("f: %s, initial: %s", bf.fno, initial.toEulerAngles())
        logger.test("f: %s, orientation: %s", bf.fno, from_orientation.toEulerAngles())

        past_direction = rep_to_pos - rep_from_pos
        past_up = MVector3D.crossProduct(past_direction, up_pos)
        past_from_orientation = MQuaternion.fromDirection(past_direction.normalized(), past_up.normalized())
        past_from_rotation = parent_qq.inverted() * cancel_qq.inverted() * past_from_orientation * initial.inverted()
        past_from_rotation.normalize()

        logger.test("f: %s, 元rep_to_pos(%s): %s", bf.fno, to_bone_name, rep_to_pos)
        logger.test("f: %s, past_direction: %s", bf.fno, past_direction)
        logger.test("f: %s, past_up: %s", bf.fno, past_up)
        logger.test("f: %s, past_from_orientation: %s", bf.fno, past_from_orientation.toEulerAngles())
        logger.test("f: %s, past_from_rotation: %s", bf.fno, past_from_rotation.toEulerAngles4MMD())

        logger.debug("f: %s, 補正回転: %s", bf.fno, from_rotation.toEulerAngles4MMD())

        org_bf = data_set.org_motion.calc_bf(from_bone_name, bf.fno)
        logger.debug("f: %s, 元の回転: %s", bf.fno, org_bf.rotation.toEulerAngles4MMD())

        if org_bf:
            # 元にもあるキーである場合、内積チェック
            uad = abs(MQuaternion.dotProduct(from_rotation.normalized(), org_bf.rotation.normalized()))
            logger.test("f: %s, uad: %s", bf.fno, uad)
            if uad < dot_limit:
                # 内積が離れすぎてたらNG
                logger.warning("%sフレーム目%sスタンス補正失敗: 角度:%s, uad: %s", bf.fno, from_bone_name, from_rotation.toEulerAngles4MMD().to_log(), uad)
            else:
                # 内積の差が小さい場合、回転適用
                bf.rotation = from_rotation
        else:
            # 元にもない場合（ないはず）、はそのまま設定
            bf.rotation = from_rotation

    # TO位置の再計算処理
    def recalc_to_pos(self, bf: VmdBoneFrame, data_set_idx: int, data_set: MOptionsDataSet, \
                      org_base_links: BoneLinks, org_from_links: BoneLinks, org_to_links: BoneLinks, org_arm_links: BoneLinks, \
                      rep_base_links: BoneLinks, rep_from_links: BoneLinks, rep_to_links: BoneLinks, rep_arm_links: BoneLinks, \
                      base_bone_name: str, from_bone_name: str, to_bone_name: str):

        # 基準ボーンまでの位置
        org_base_global_3ds, org_front_base_global_3ds, org_base_direction_qq = \
            MServiceUtils.calc_front_global_pos(data_set.org_model, org_base_links, data_set.org_motion, bf.fno, org_from_links)
        rep_base_global_3ds, rep_front_base_global_3ds, rep_base_direction_qq = \
            MServiceUtils.calc_front_global_pos(data_set.rep_model, rep_base_links, data_set.motion, bf.fno, rep_from_links)

        # # 基準ボーンの位置
        # org_base_pos = org_base_global_3ds[base_bone_name]
        rep_base_pos = rep_base_global_3ds[base_bone_name]

        # 正面向きの基準ボーンの位置
        org_front_base_pos = org_front_base_global_3ds[base_bone_name]
        rep_front_base_pos = rep_front_base_global_3ds[base_bone_name]

        # -------------

        # TOボーンまでの位置（フレームはFROMまでで、TO自身は初期値として求める）
        org_to_global_3ds, org_front_to_global_3ds, org_to_direction_qq = \
            MServiceUtils.calc_front_global_pos(data_set.org_model, org_to_links, data_set.org_motion, bf.fno, org_from_links)
        rep_to_global_3ds, rep_front_to_global_3ds, rep_to_direction_qq = \
            MServiceUtils.calc_front_global_pos(data_set.rep_model, rep_to_links, data_set.motion, bf.fno, rep_from_links)

        # TOボーンの正面位置
        org_front_to_pos = org_front_to_global_3ds[to_bone_name]
        rep_front_to_pos = rep_front_to_global_3ds[to_bone_name]

        # -------------

        # TOの長さ比率

        # 肩幅比率
        org_arm_diff = (org_arm_links["左"].get("左腕").position - org_arm_links["右"].get("右腕").position)
        rep_arm_diff = (rep_arm_links["左"].get("左腕").position - rep_arm_links["右"].get("右腕").position)
        arm_diff_ratio = rep_arm_diff / org_arm_diff
        arm_diff_ratio.one()    # 比率なので、0は1に変換する

        # TOの長さ比率
        org_to_diff = (org_to_links.get(to_bone_name).position - org_base_links.get(base_bone_name).position)
        org_to_diff.abs()
        rep_to_diff = (rep_to_links.get(to_bone_name).position - rep_base_links.get(base_bone_name).position)
        rep_to_diff.abs()
        to_diff_ratio = rep_to_diff / org_to_diff
        
        logger.test("f: %s, arm_diff_ratio: %s", bf.fno, arm_diff_ratio)
        logger.test("f: %s, to_diff_ratio: %s", bf.fno, to_diff_ratio)

        # ---------------
        
        rep_front_to_x = rep_front_base_pos.x() + ((org_front_to_pos.x() - org_front_base_pos.x()) * arm_diff_ratio.x())
        rep_front_to_y = rep_front_base_pos.y() + ((org_front_to_pos.y() - org_front_base_pos.y()) * to_diff_ratio.y())
        rep_front_to_z = rep_front_base_pos.z() + ((org_front_to_pos.z() - org_front_base_pos.z()) * arm_diff_ratio.x())

        logger.test("f: %s, rep_front_base_pos: %s", bf.fno, rep_front_base_pos)
        logger.test("f: %s, org_front_to_pos: %s", bf.fno, org_front_to_pos)
        logger.test("f: %s, org_front_base_pos: %s", bf.fno, org_front_base_pos)

        new_rep_front_to_pos = MVector3D(rep_front_to_x, rep_front_to_y, rep_front_to_z)
        logger.test("f: %s, 計算new_rep_front_to_pos: %s", bf.fno, new_rep_front_to_pos)
        logger.test("f: %s, 元rep_front_to_pos: %s", bf.fno, rep_front_to_pos)

        # 正面向きの新しいTO位置
        new_rep_front_to_global_3ds = copy.deepcopy(rep_front_to_global_3ds)
        new_rep_front_to_global_3ds[to_bone_name] = new_rep_front_to_pos

        # 回転を元に戻した位置
        rotated_to_3ds = MServiceUtils.calc_global_pos_by_direction(rep_to_direction_qq, new_rep_front_to_global_3ds)

        return rotated_to_3ds[to_bone_name], rep_to_global_3ds[to_bone_name], rep_base_pos, rep_to_global_3ds[from_bone_name]

    # スタンス用細分化
    def prepare_split_stance(self, data_set_idx: int, data_set: MOptionsDataSet, target_bone_name: str):
        motion = data_set.motion
        fnos = motion.get_bone_fnos(target_bone_name)

        for fidx, fno in enumerate(fnos):
            if fidx == 0:
                continue

            prev_bf = motion.bones[target_bone_name][fnos[fidx - 1]]
            bf = motion.bones[target_bone_name][fno]

            # 内積で離れ具合をチェック
            dot = MQuaternion.dotProduct(prev_bf.rotation, bf.rotation)
            if abs(dot) < 0.2:
                # 回転量が約150度以上の場合、半分に分割しておく
                half_fno = prev_bf.fno + round((bf.fno - prev_bf.fno) / 2)

                if bf.fno < half_fno < prev_bf.fno:
                    # キーが追加できる状態であれば、追加
                    motion.split_bf_by_fno(target_bone_name, prev_bf, bf, half_fno)

    # 腕スタンス補正
    def adjust_arm_stance(self, data_set_idx: int, data_set: MOptionsDataSet):
        logger.info("腕スタンス補正　【No.%s】", (data_set_idx + 1), decoration=MLogger.DECORATION_LINE)
        
        # 腕のスタンス差
        arm_diff_qq_dic = self.calc_arm_stance(data_set)

        for direction in ["左", "右"]:
            for bone_type in ["腕", "ひじ", "手首"]:
                bone_name = "{0}{1}".format(direction, bone_type)

                if bone_name in arm_diff_qq_dic and bone_name in data_set.motion.bones:
                    # スタンス補正値がある場合
                    for bf in data_set.motion.bones[bone_name].values():
                        if bf.key:
                            if arm_diff_qq_dic[bone_name]["from"] == MQuaternion():
                                bf.rotation = bf.rotation * arm_diff_qq_dic[bone_name]["to"]
                            else:
                                bf.rotation = arm_diff_qq_dic[bone_name]["from"].inverted() * bf.rotation * arm_diff_qq_dic[bone_name]["to"]
                    
                    logger.info("腕スタンス補正: %s", bone_name)
                    logger.test("from: %s", arm_diff_qq_dic[bone_name]["from"].toEulerAngles())
                    logger.test("to: %s", arm_diff_qq_dic[bone_name]["to"].toEulerAngles())

    # 腕スタンス補正用傾き計算
    def calc_arm_stance(self, data_set: MOptionsDataSet):
        arm_diff_qq_dic = {}

        for direction in ["左", "右"]:
            for from_bone_type, target_bone_type, to_bone_type in [(None, "腕", "ひじ"), ("腕", "ひじ", "手首"), ("ひじ", "手首", "中指１")]:
                from_bone_name = "{0}{1}".format(direction, from_bone_type) if from_bone_type else None
                target_bone_name = "{0}{1}".format(direction, target_bone_type)
                to_bone_name = "{0}{1}".format(direction, to_bone_type)

                if from_bone_name:
                    bone_names = [from_bone_name, target_bone_name, to_bone_name]
                else:
                    bone_names = [target_bone_name, to_bone_name]

                if set(bone_names).issubset(data_set.org_model.bones) and set(bone_names).issubset(data_set.rep_model.bones):
                    # 対象ボーンが揃っている場合（念のためバラバラにチェック）

                    # 揃ってたら辞書登録
                    arm_diff_qq_dic[target_bone_name] = {}

                    if from_bone_name:
                        # FROM-TARGETの傾き
                        _, org_from_qq = data_set.org_model.calc_arm_stance(from_bone_name, target_bone_name)
                        _, rep_from_qq = data_set.rep_model.calc_arm_stance(from_bone_name, target_bone_name)

                        arm_diff_qq_dic[target_bone_name]["from"] = rep_from_qq.inverted() * org_from_qq
                    else:
                        arm_diff_qq_dic[target_bone_name]["from"] = MQuaternion()

                    # TARGET-TOの傾き
                    _, org_to_qq = data_set.org_model.calc_arm_stance(target_bone_name, to_bone_name)
                    _, rep_to_qq = data_set.rep_model.calc_arm_stance(target_bone_name, to_bone_name)

                    arm_diff_qq_dic[target_bone_name]["to"] = rep_to_qq.inverted() * org_to_qq
        
        return arm_diff_qq_dic


