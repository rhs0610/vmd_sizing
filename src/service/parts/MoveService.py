# -*- coding: utf-8 -*-
#
import os
import logging # noqa
import numpy as np
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from module.MOptions import MOptions, MOptionsDataSet
from utils import MServiceUtils, MBezierUtils # noqa
from utils.MLogger import MLogger # noqa
from utils.MException import SizingException, MKilledException


logger = MLogger(__name__, level=logging.DEBUG)


class MoveService():
    def __init__(self, options: MOptions):
        self.options = options

    def execute(self):
        futures = []

        with ThreadPoolExecutor(thread_name_prefix="move", max_workers=min(5, self.options.max_workers)) as executor:
            for data_set_idx, data_set in enumerate(self.options.data_set_list):
                if data_set.motion.motion_cnt <= 0:
                    # モーションデータが無い場合、処理スキップ
                    continue

                logger.info("이동 보정　【No.%s】", (data_set_idx + 1), decoration=MLogger.DECORATION_LINE)

                # センターのY軸오프셋を計算
                self.set_center_y_offset(data_set_idx, data_set)

                # センターのZ軸오프셋を計算
                self.set_center_z_offset(data_set_idx, data_set)

                # 足IKの오프셋を計算
                self.set_leg_ik_offset(data_set_idx, data_set)

                for bone_name in ["全ての親", "センター", "グルーブ", "右足IK親", "左足IK親", "右足ＩＫ", "左足ＩＫ", "右つま先ＩＫ", "左つま先ＩＫ"]:
                    if bone_name in data_set.motion.bones and bone_name in data_set.rep_model.bones and len(data_set.motion.bones[bone_name].keys()) > 0:
                        futures.append(executor.submit(self.adjust_move, data_set_idx, bone_name))

                if self.options.now_process_ctrl:
                    self.options.now_process += 1
                    self.options.now_process_ctrl.write(str(self.options.now_process))

                    proccess_key = "【No.{0}】{1}({2})".format(data_set_idx + 1, os.path.basename(data_set.motion.path), data_set.rep_model.name)
                    self.options.tree_process_dict[proccess_key]["이동 축척 보정"] = True

        concurrent.futures.wait(futures, timeout=None, return_when=concurrent.futures.FIRST_EXCEPTION)

        for f in futures:
            if not f.result():
                return False

        return True

    def adjust_move(self, data_set_idx: int, bone_name: str):
        try:
            logger.copy(self.options)
            data_set = self.options.data_set_list[data_set_idx]
            fnos = data_set.motion.get_bone_fnos(bone_name)
            bone_link = data_set.rep_model.create_link_2_top_one(bone_name)

            for fno in fnos:
                bf = data_set.motion.bones[bone_name][fno]

                # 一旦IK比率をそのまま掛ける
                bf.position.setX(bf.position.x() * data_set.xz_ratio)
                bf.position.setY(bf.position.y() * data_set.y_ratio)
                bf.position.setZ(bf.position.z() * data_set.xz_ratio)

                _, rep_global_mats = MServiceUtils.calc_global_pos(data_set.rep_model, bone_link, data_set.motion, fno, return_matrix=True)
                # 該当ボーンのローカル位置
                local_pos = rep_global_mats[bone_name].inverted() * bf.position
                # ローカル位置に오프셋調整
                local_pos += data_set.rep_model.bones[bone_name].local_offset
                # 元に戻す
                bf.position = rep_global_mats[bone_name] * local_pos

            if len(fnos) > 0:
                logger.info("이동보정:종료【No.%s - %s】", data_set_idx + 1, bone_name)

            return True
        except MKilledException as ke:
            raise ke
        except SizingException as se:
            logger.error("사이징 처리가 처리할 수 없는 데이터로 종료되었습니다.\n\n%s", se.message)
            return se
        except Exception as e:
            import traceback
            logger.error("사이징 처리가 의도치 않은 오류로 종료되었습니다.\n\n%s", traceback.format_exc())
            raise e

    def set_leg_ik_offset(self, data_set_idx: int, data_set: MOptionsDataSet):
        target_bones = ["左足", "左足ＩＫ", "右足ＩＫ"]

        if set(target_bones).issubset(data_set.org_model.bones) and set(target_bones).issubset(data_set.rep_model.bones):
            # 足ボーンの差(orgを元にするので比率反転)
            leg_ratio = 1 / data_set.original_xz_ratio

            # 足IKの오프셋上限
            leg_ik_offset = {"左": MVector3D(), "右": MVector3D()}
            for direction in ["左", "右"]:
                org_leg_ik_pos = data_set.org_model.bones["{0}足ＩＫ".format(direction)].position
                rep_leg_ik_global_pos = data_set.rep_model.bones["{0}足ＩＫ".format(direction)].position
                org_leg_pos = data_set.org_model.bones["{0}足".format(direction)].position
                rep_leg_pos = data_set.rep_model.bones["{0}足".format(direction)].position
                # IK오프셋
                leg_ik_offset[direction] = ((org_leg_ik_pos - org_leg_pos) * leg_ratio) - (rep_leg_ik_global_pos - rep_leg_pos)
                leg_ik_offset[direction].effective()
                leg_ik_offset[direction].setY(0)
                leg_ik_offset[direction].setZ(0)
                logger.debug("leg_ik_offset(%s): %s", direction, leg_ik_offset[direction])

                if abs(leg_ik_offset[direction].x() * data_set.original_xz_ratio) > abs(rep_leg_ik_global_pos.x()):
                    # IK오프셋が、元々の足の位置の一定以上に広がっている場合、縮める
                    re_x = (rep_leg_ik_global_pos.x() - (leg_ik_offset[direction].x() * data_set.original_xz_ratio)) * data_set.original_xz_ratio
                    # 오프셋の広がり具合が、元々と同じ場合は正、反対の場合、負
                    leg_ik_offset[direction].setX(re_x * (1 if np.sign(leg_ik_offset[direction].x()) == np.sign(rep_leg_ik_global_pos.x()) else -1))

                # 指定値加算
                specified_leg_offset = 0
                if data_set_idx in self.options.leg_options.leg_offsets:
                    specified_leg_offset = self.options.leg_options.leg_offsets[data_set_idx] * np.sign(rep_leg_ik_global_pos.x())

                leg_ik_offset[direction].setX(leg_ik_offset[direction].x() + specified_leg_offset)
                logger.debug("specified_leg_offset(%s): %s -> %s", direction, specified_leg_offset, leg_ik_offset[direction].x())

            logger.info("【No.%s】IK오프셋(%s): x: %s, z: %s", (data_set_idx + 1), "左足", leg_ik_offset["左"].x(), leg_ik_offset["左"].z())
            logger.info("【No.%s】IK오프셋(%s): x: %s, z: %s", (data_set_idx + 1), "右足", leg_ik_offset["右"].x(), leg_ik_offset["右"].z())

            if "左足IK親" in data_set.rep_model.bones and "左足IK親" in data_set.motion.bones:
                # IK親があって使われている場合、IK親に오프셋設定
                data_set.rep_model.bones["左足IK親"].local_offset = leg_ik_offset["左"]
            else:
                data_set.rep_model.bones["左足ＩＫ"].local_offset = leg_ik_offset["左"]

            if "右足IK親" in data_set.rep_model.bones and "右足IK親" in data_set.motion.bones:
                # IK親があって使われている場合、IK親に오프셋設定
                data_set.rep_model.bones["右足IK親"].local_offset = leg_ik_offset["右"]
            else:
                data_set.rep_model.bones["右足ＩＫ"].local_offset = leg_ik_offset["右"]

            return

        logger.info("IK 오프셋 없음.")

    # センターY오프셋計算
    def set_center_y_offset(self, data_set_idx: int, data_set: MOptionsDataSet):
        target_bones = ["左足", "左ひざ", "左足首", "センター"]

        if set(target_bones).issubset(data_set.org_model.bones) and set(target_bones).issubset(data_set.rep_model.bones):
            specified_leg_offset = 0
            if data_set_idx in self.options.leg_options.leg_offsets:
                specified_leg_offset = self.options.leg_options.leg_offsets[data_set_idx]

            # 変換先モデルの足首の位置は足ＩＫ오프셋を加味する
            rep_ankle_pos = data_set.rep_model.bones["左足首"].position - MVector3D(specified_leg_offset, 0, 0)
            # 元モデルの足の長さ比
            org_leg_upper_length = (data_set.org_model.bones["左ひざ"].position.distanceToPoint(data_set.org_model.bones["左足"].position))
            org_leg_lower_length = (data_set.org_model.bones["左ひざ"].position.distanceToPoint(rep_ankle_pos))
            org_leg_ik_length = (data_set.org_model.bones["左足"].position - rep_ankle_pos).y()
            logger.test("org_leg_upper_length: %s", org_leg_upper_length)
            logger.test("org_leg_lower_length: %s", org_leg_lower_length)
            logger.test("org_leg_ik_length: %s", org_leg_ik_length)

            # 足ボーンの長さとIKの長さ比
            org_leg_ratio = org_leg_ik_length / (org_leg_upper_length + org_leg_lower_length)
            logger.test("org_leg_ratio: %s", org_leg_ratio)

            # 先モデルの足の長さ比
            rep_leg_upper_length = (data_set.rep_model.bones["左ひざ"].position.distanceToPoint(data_set.rep_model.bones["左足"].position))
            rep_leg_lower_length = (data_set.rep_model.bones["左ひざ"].position.distanceToPoint(data_set.rep_model.bones["左足首"].position))
            rep_leg_ik_length = (data_set.rep_model.bones["左足"].position - data_set.rep_model.bones["左足首"].position).y()
            logger.test("rep_leg_upper_length: %s", rep_leg_upper_length)
            logger.test("rep_leg_lower_length: %s", rep_leg_lower_length)
            logger.test("rep_leg_ik_length: %s", rep_leg_ik_length)

            # 元モデルの長さ比から、足IKの長さ比を再算出
            rep_recalc_ik_length = org_leg_ratio * (rep_leg_upper_length + rep_leg_lower_length)
            logger.test("rep_recalc_ik_length: %s", rep_recalc_ik_length)

            if rep_recalc_ik_length < rep_leg_ik_length:
                # 再算出した長さが本来のIKの長さより小さい場合（足が曲がってる場合）

                # センターYを少し縮めて、足の辺比率を同じにする
                offset_y = rep_recalc_ik_length - rep_leg_ik_length

                data_set.rep_model.bones["センター"].local_offset.setY(offset_y)
                logger.test("local_offset %s", data_set.rep_model.bones["センター"].local_offset)

                logger.info("【No.%s】센터 Y 오프셋: %s", (data_set_idx + 1), offset_y)

                return

            logger.info("【No.%s】센터 Y 오프셋 없음", (data_set_idx + 1))

    # センターZ오프셋計算
    def set_center_z_offset(self, data_set_idx: int, data_set: MOptionsDataSet):
        target_bones = ["左つま先ＩＫ", "左足", "左足首", "センター"]

        if set(target_bones).issubset(data_set.org_model.bones) and set(target_bones).issubset(data_set.rep_model.bones):
            # 作成元センターのZ位置
            org_center_z = data_set.org_model.bones["センター"].position.z()
            logger.test("org_center_z: %s", org_center_z)
            # 作成元左足首のZ位置
            org_ankle_z = data_set.org_model.bones["左足首"].position.z()
            logger.test("org_ankle_z: %s", org_ankle_z)
            # 作成元左足のZ位置
            org_leg_z = data_set.org_model.bones["左足"].position.z()
            logger.test("org_leg_z: %s", org_leg_z)
            # 作成元つま先のZ位置
            org_toe_z = data_set.org_model.left_toe_vertex.position.z()
            logger.test("org_toe_z: %s", org_toe_z)

            # 変換先センターのZ位置
            rep_center_z = data_set.rep_model.bones["センター"].position.z()
            logger.test("rep_center_z: %s", rep_center_z)
            # 変換先左足首のZ位置
            rep_ankle_z = data_set.rep_model.bones["左足首"].position.z()
            logger.test("rep_ankle_z: %s", rep_ankle_z)
            # 変換先左足のZ位置
            rep_leg_z = data_set.rep_model.bones["左足"].position.z()
            logger.test("rep_leg_z: %s", rep_leg_z)
            # 変換先つま先のZ位置
            rep_toe_z = data_set.rep_model.left_toe_vertex.position.z()
            logger.test("rep_toe_z: %s", rep_toe_z)

            # 作成元の足の長さ
            org_leg_zlength = org_ankle_z - org_toe_z
            # 作成元の重心
            org_center_gravity = (org_ankle_z - org_leg_z) / (org_ankle_z - org_toe_z)
            logger.test("org_center_gravity %s, org_leg_zlength: %s", org_center_gravity, org_leg_zlength)

            # 変換先の足の長さ
            rep_leg_zlength = rep_ankle_z - rep_toe_z
            # 変換先の重心
            rep_center_gravity = (rep_ankle_z - rep_leg_z) / (rep_ankle_z - rep_toe_z)
            logger.test("rep_center_gravity %s, rep_leg_zlength: %s", rep_center_gravity, rep_leg_zlength)

            local_offset_z = (rep_center_gravity - org_center_gravity) * (rep_leg_zlength / org_leg_zlength)
            data_set.rep_model.bones["センター"].local_offset.setZ(local_offset_z)
            logger.test("local_offset %s", data_set.rep_model.bones["センター"].local_offset)

            logger.info("【No.%s】센터 Z 오프셋: %s", (data_set_idx + 1), local_offset_z)

            return

        logger.info("【No.%s】센터 Z 오프셋 없음", (data_set_idx + 1))



