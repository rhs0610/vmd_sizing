# -*- coding: utf-8 -*-
#
import os
import numpy as np
import math
import itertools
from libc.math cimport sin, cos, acos, atan2, asin, pi, sqrt

import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

from module.MParams import BoneLinks # noqa
from module.MParams cimport BoneLinks # noqa

from module.MMath import MRect, MVector2D, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from module.MMath cimport MRect, MVector2D, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa

from mmd.PmxData import PmxModel, OBB, Bone, Vertex, Material, Morph, DisplaySlot, RigidBody, Joint # noqa
from mmd.PmxData cimport PmxModel, OBB, Bone, RigidBody

from mmd.VmdData import VmdMotion, VmdBoneFrame, VmdCameraFrame, VmdInfoIk, VmdLightFrame, VmdMorphFrame, VmdShadowFrame, VmdShowIkFrame # noqa
from mmd.VmdData cimport VmdMotion, VmdBoneFrame

from module.MOptions import MOptions, MOptionsDataSet # noqa
from module.MOptions cimport MOptions, MOptionsDataSet # noqa

from utils import MServiceUtils
from utils cimport MServiceUtils

from utils.MLogger import MLogger # noqa
from utils.MException import SizingException, MKilledException

logger = MLogger(__name__, level=1)

# 床処理用INDEX
cdef int FLOOR_IDX = -1


# 위치 맞춤用オプション
cdef class ArmAlignmentOption:
    cdef public BoneLinks org_links
    cdef public BoneLinks rep_links
    cdef public list ik_links_list
    cdef public list ik_count_list
    cdef public BoneLinks tip_ik_links
    cdef public double org_palm_length
    cdef public double rep_palm_length
    cdef public str start_bone_name
    cdef public str effector_bone_name
    cdef public str effector_display_bone_name
    cdef public double distance
    cdef public str tip_bone_name
    cdef public int priority
    cdef public double ratio
    cdef public double multi_ratio

    def __init__(self, org_links: BoneLinks, rep_links: BoneLinks, ik_links_list: list, ik_count_list: list, tip_ik_links: BoneLinks, \
                 org_palm_length: float, rep_palm_length: float, org_model: PmxModel, rep_model: PmxModel, start_bone_name: str, \
                 effector_bone_name: str, effector_display_bone_name: str, tip_bone_name: str, distance: float, xz_ratio: float, priority: int):
        super().__init__()

        self.org_links = org_links
        self.rep_links = rep_links
        self.ik_links_list = ik_links_list
        self.ik_count_list = ik_count_list
        self.tip_ik_links = tip_ik_links
        self.org_palm_length = org_palm_length
        self.rep_palm_length = rep_palm_length
        self.start_bone_name = start_bone_name
        self.effector_bone_name = effector_bone_name
        self.effector_display_bone_name = effector_display_bone_name
        self.distance = distance
        self.tip_bone_name = tip_bone_name
        self.priority = priority

        if "床" in start_bone_name:
            # 元と先の比率（床の場合、XZ比率で身体の大きさだけ検討する）
            self.ratio = xz_ratio
        else:
            # エフェクタまでの長さ比率
            org_effector_diff = (org_model.bones[effector_bone_name].position - org_model.bones[start_bone_name].position)
            org_effector_diff.one()
            rep_effector_diff = (rep_model.bones[effector_bone_name].position - rep_model.bones[start_bone_name].position)
            rep_effector_diff.one()
            effector_diff_ratio = rep_effector_diff.length() / org_effector_diff.length()

            # 元と先の比率
            self.ratio = effector_diff_ratio
        # 元と先の比率（複数モーション時）
        self.multi_ratio = xz_ratio


cdef class ArmAlignmentService:
    cdef public object options
    cdef public list target_data_set_idxs
    cdef public dict target_links

    def __init__(self, options: MOptions):
        self.options = options

    def execute(self):
        # 腕処理対象データセットを取得
        self.target_data_set_idxs = self.get_target_set_idxs()
        logger.test("target_data_set_idxs: %s", self.target_data_set_idxs)

        if len(self.target_data_set_idxs) == 0:
            # データセットがない場合、処理スキップ
            logger.warning("위치 맞춤을 할 수 있는 파일 세트를 찾지 못했기 때문에 위치 맞춤 처리를 건너뛰습니다.", decoration=MLogger.DECORATION_BOX)
            return True

        # リンク辞書
        self.target_links = {}
        # 処理対象ボーン名リスト
        bone_names = ["センター", "グルーブ"]

        logger.info("위치 맞춤", decoration=MLogger.DECORATION_LINE)

        try:
            for data_set_idx in self.target_data_set_idxs:
                # 処理対象データセットに対して、準備실행

                # 手首위치 맞춤用準備（床위치 맞춤も含む）
                bone_names.extend(self.prepare_wrist(data_set_idx))

                if self.options.arm_options.alignment_finger_flg:
                    # 指위치 맞춤用準備
                    bone_names.extend(self.prepare_finger(data_set_idx))

            # ボーン名重複除去
            bone_names = list(set(bone_names))

            fnos = []
            # 処理対象全ファイルセット単位でキーフレ検出
            for data_set_idx in self.target_data_set_idxs:
                # 処理対象データセット
                data_set = self.options.data_set_list[data_set_idx]
                fnos.extend(data_set.motion.get_bone_fnos(*bone_names))

            # キーフレを重複除外してソートする
            fnos = sorted(list(set(fnos)))

            # 위치 맞춤 준비
            all_alignment_group_list, all_messages = self.prepare_alignment(fnos)

            # 위치 맞춤실행
            self.execute_alignment(fnos, all_alignment_group_list, all_messages, bone_names)

            if self.options.now_process_ctrl:
                self.options.now_process += 1
                self.options.now_process_ctrl.write(str(self.options.now_process))

                self.options.tree_process_dict["위치 맞춤"] = True

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

    # 위치 맞춤 준비
    cdef prepare_alignment(self, list fnos):
        cdef int from_data_set_idx, to_data_set_idx, alignment_idx, data_set_idx, fidx, from_alignment_idx
        cdef int group_idx, to_alignment_idx, fno, priority, prev_block_fno
        cdef double base_distance, distance, distance_ratio, org_palm_mean
        cdef dict alignment_options, all_alignment_group, all_distances, all_is_alignment, all_messages, all_org_global_effector_matrixs, all_org_global_effector_vec
        cdef dict all_org_global_neck_vec, all_org_global_tip_vec, all_org_global_trunk_matrixs, all_org_global_upper_vec, distances, org_global_3ds, org_global_matrixs
        cdef dict all_alignment_idx
        cdef list alignment_pairs, all_alignment_group_list, org_effector_pairs, target_pairs
        cdef str link_name
        cdef bint is_alignment, is_floor, is_sit, prev_from_alignment, prev_to_alignment
        cdef VmdBoneFrame bf
        cdef MOptionsDataSet data_set, from_data_set, to_data_set
        cdef ArmAlignmentOption from_target_link, target_link, to_target_link
        cdef BoneLinks ik_links
        cdef MMatrix4x4 org_effector_matrix, org_origin_matrix, org_trunk_matrix
        cdef MVector3D org_fno_mean_vec, org_from_global_effector_vec, org_global_effector, org_global_tip, org_local_tip, org_mean_vec, org_to_global_effector_vec
        cdef MVector3D org_trunk_local_fno_effector, org_trunk_local_fno_origin

        all_org_global_effector_vec = {}
        all_org_global_trunk_matrixs = {}
        all_org_global_neck_vec = {}
        all_org_global_upper_vec = {}
        all_org_global_tip_vec = {}
        all_org_global_effector_matrixs = {}

        prev_block_fno = 0
        target_pairs = []
        for data_set_idx, alignment_options in self.target_links.items():
            for alignment_idx, target_link in alignment_options.items():
                target_pairs.append((data_set_idx, alignment_idx))

        org_effector_pairs = list(itertools.combinations(target_pairs, 2))
        logger.test("list: %s, pairs: %s", target_pairs, org_effector_pairs)

        for fno in fnos:
            all_org_global_effector_vec[fno] = {}
            all_org_global_trunk_matrixs[fno] = {}
            all_org_global_neck_vec[fno] = {}
            all_org_global_upper_vec[fno] = {}
            all_org_global_tip_vec[fno] = {}
            all_org_global_effector_matrixs[fno] = {}

            # 処理対象キーフレを先頭からひとつずつチェックしていく
            for data_set_idx, alignment_options in self.target_links.items():
                for alignment_idx, target_link in alignment_options.items():
                    # 処理対象データセット
                    data_set = self.options.data_set_list[data_set_idx]

                    # 원본 모델のそれぞれのグローバル位置
                    org_global_3ds, org_global_matrixs = \
                        MServiceUtils.c_calc_global_pos(data_set.org_model, target_link.org_links, data_set.org_motion, fno, return_matrix=True, is_local_x=True, limit_links=None)

                    all_org_global_effector_vec[fno][(data_set_idx, alignment_idx)] = org_global_3ds[target_link.effector_bone_name]

                    if alignment_idx < 0:
                        # 床の位置は各位置のY0をvectorの場合のみ定義し直す（距離を測る用）
                        all_org_global_effector_vec[fno][(data_set_idx, alignment_idx)].setY(0)

                    all_org_global_trunk_matrixs[fno][(data_set_idx, alignment_idx)] = org_global_matrixs["首根元"]
                    all_org_global_neck_vec[fno][(data_set_idx, alignment_idx)] = org_global_3ds["首根元"]
                    all_org_global_upper_vec[fno][(data_set_idx, alignment_idx)] = org_global_3ds["上半身"]

                    if target_link.tip_ik_links:
                        # 指先合わせが必要な場合、保持
                        all_org_global_tip_vec[fno][(data_set_idx, alignment_idx)] = org_global_3ds[target_link.tip_bone_name]
                        all_org_global_effector_matrixs[fno][(data_set_idx, alignment_idx)] = org_global_matrixs[target_link.effector_bone_name]

            if fno // 200 > prev_block_fno:
                logger.count("위치 맞춤 준비 ①", fno, fnos)
                prev_block_fno = fno // 200

        logger.count("위치 맞춤 준비①", fno, fnos)

        all_messages = {}
        all_is_alignment = {}
        all_alignment_idx = {}
        all_distances = {}

        for data_set_idx, alignment_options in self.target_links.items():
            for alignment_idx, target_link in alignment_options.items():
                # indexを保持
                all_is_alignment[(data_set_idx, alignment_idx)] = {}
                all_alignment_idx[(data_set_idx, alignment_idx)] = -1

        for fno in fnos:
            distances = {}
            all_messages[fno] = []
            all_distances[fno] = {}

            # それぞれの距離を算出
            # 起点となるボーン
            for ((from_data_set_idx, from_alignment_idx), (to_data_set_idx, to_alignment_idx)) in org_effector_pairs:
                org_from_global_effector_vec = all_org_global_effector_vec[fno][(from_data_set_idx, from_alignment_idx)]
                org_to_global_effector_vec = all_org_global_effector_vec[fno][(to_data_set_idx, to_alignment_idx)]

                # 処理対象
                from_target_link = self.target_links[from_data_set_idx][from_alignment_idx]
                to_target_link = self.target_links[to_data_set_idx][to_alignment_idx]

                # 同じINDEX、同じ方向で同じ計算対象
                if (from_data_set_idx, from_target_link.start_bone_name[0]) == (to_data_set_idx, to_target_link.start_bone_name[0]) or \
                        (from_data_set_idx, from_alignment_idx, to_data_set_idx, to_alignment_idx) in distances or \
                        (to_data_set_idx, to_alignment_idx, from_data_set_idx, from_alignment_idx) in distances:
                    # 同じ計算対象のペアは計算不要（同じ手首の指同士を想定）
                    continue

                if (from_alignment_idx < 0 or to_alignment_idx < 0) and (from_data_set_idx != to_data_set_idx or from_alignment_idx != to_alignment_idx * -1):
                    # 床は自分自身とのみ調整
                    continue

                # 2点間の距離を算出
                distances[(from_data_set_idx, from_alignment_idx, to_data_set_idx, to_alignment_idx)] \
                    = org_from_global_effector_vec.distanceToPoint(org_to_global_effector_vec)

            logger.test("fno: %s, distances: %s", fno, distances)

            for (from_data_set_idx, from_alignment_idx, to_data_set_idx, to_alignment_idx), distance in distances.items():
                # 距離を2点間の比率の平均から比率として求める
                org_palm_mean = np.mean([self.target_links[from_data_set_idx][from_alignment_idx].ratio, self.target_links[to_data_set_idx][to_alignment_idx].ratio])
                distance_ratio = distance / org_palm_mean

                # 基準距離（床は床위치 맞춤の距離が入ってる）
                base_distance = self.target_links[to_data_set_idx][to_alignment_idx].distance
                # 基準距離以内か常に위치 맞춤を行うかの場合、위치 맞춤処理실행
                is_alignment = 0 < distance_ratio <= base_distance or base_distance == 10

                logger.test("f: %s, (%s,%s,%s,%s): org_palm_mean: %s, distance: %s, distance_ratio: %s, base_distance: %s, is_alignment: %s", fno, from_data_set_idx, from_alignment_idx, \
                            to_data_set_idx, to_alignment_idx, org_palm_mean, distance, distance_ratio, base_distance, is_alignment)

                # 優先順位・距離をキーにして、INDEXの組合せを登録
                priority = self.target_links[to_data_set_idx][to_alignment_idx].priority
                if priority not in all_distances[fno]:
                    all_distances[fno][priority] = {}

                if distance_ratio not in all_distances[fno][priority]:
                    all_distances[fno][priority][distance_ratio] = []

                if (from_data_set_idx, from_alignment_idx, to_data_set_idx, to_alignment_idx, is_alignment) not in all_distances[fno][priority][distance_ratio]:
                    all_distances[fno][priority][distance_ratio].append((from_data_set_idx, from_alignment_idx, to_data_set_idx, to_alignment_idx, is_alignment))

                    if fno not in all_is_alignment[(from_data_set_idx, from_alignment_idx)]:
                        all_is_alignment[(from_data_set_idx, from_alignment_idx)][fno] = is_alignment
                    else:
                        all_is_alignment[(from_data_set_idx, from_alignment_idx)][fno] = is_alignment or all_is_alignment[(from_data_set_idx, from_alignment_idx)][fno]

                    if fno not in all_is_alignment[(to_data_set_idx, to_alignment_idx)]:
                        all_is_alignment[(to_data_set_idx, to_alignment_idx)][fno] = is_alignment
                    else:
                        all_is_alignment[(to_data_set_idx, to_alignment_idx)][fno] = is_alignment or all_is_alignment[(to_data_set_idx, to_alignment_idx)][fno]

            if fno // 500 > prev_block_fno:
                logger.count("위치 맞춤 준비②", fno, fnos)
                prev_block_fno = fno // 500

        logger.count("위치 맞춤 준비②", fno, fnos)

        all_alignment_group_list = []
        prev_block_fno = 0

        # 優先順位が高いもの、同優先順位では距離の近いものからINDEXの組合せを登録
        # 基本的には全部の中心点を算出するが、それぞれのモデルの両手のみが近かった場合を想定
        for fidx, fno in enumerate(all_distances.keys()):
            is_alignment_by_priority = False
            for priority in sorted(all_distances[fno].keys()):
                alignment_pairs = []
                for distance_ratio in sorted(all_distances[fno][priority].keys()):
                    for from_data_set_idx, from_alignment_idx, to_data_set_idx, to_alignment_idx, is_alignment in all_distances[fno][priority][distance_ratio]:
                        is_alignment_by_priority = is_alignment_by_priority or is_alignment
                        # 前回の위치 맞춤
                        prev_from_alignment = False if fidx == 0 else all_is_alignment[(from_data_set_idx, from_alignment_idx)][list(all_distances.keys())[fidx - 1]]
                        prev_to_alignment = False if fidx == 0 else all_is_alignment[(to_data_set_idx, to_alignment_idx)][list(all_distances.keys())[fidx - 1]]

                        # 処理対象データセット
                        from_data_set = self.options.data_set_list[from_data_set_idx]
                        to_data_set = self.options.data_set_list[to_data_set_idx]
                        # 処理対象
                        from_target_link = self.target_links[from_data_set_idx][from_alignment_idx]
                        to_target_link = self.target_links[to_data_set_idx][to_alignment_idx]

                        # 首が上半身よりも大体上の場合、座ってる可能性（床위치 맞춤可）
                        is_sit = all_org_global_neck_vec[fno][(to_data_set_idx, to_alignment_idx)].y() * 1.2 > all_org_global_upper_vec[fno][(to_data_set_idx, to_alignment_idx)].y()

                        if (from_data_set_idx, from_target_link.effector_bone_name[0]) in alignment_pairs or \
                                (to_data_set_idx, to_target_link.effector_bone_name[0]) in alignment_pairs:
                            # 既にその方向の위치 맞춤が発生している場合、위치 맞춤OFF
                            continue

                        # 위치 맞춤する方向
                        alignment_pairs.append((from_data_set_idx, from_target_link.effector_bone_name[0]))
                        alignment_pairs.append((to_data_set_idx, to_target_link.effector_bone_name[0]))

                        if is_alignment:
                            # 首根元が床に近い場合、寝転んでる可能性が高いので위치 맞춤不要
                            # 위치 맞춤する場合

                            # 前回既に위치 맞춤が必要であった場合、そのINDEXを使用する
                            if prev_from_alignment and (from_data_set_idx, from_target_link.effector_bone_name[0]) in all_alignment_idx and \
                                    all_alignment_idx[(from_data_set_idx, from_target_link.effector_bone_name[0])] >= 0:
                                # FROM前回が위치 맞춤ONの場合、FROMに寄せる
                                alignment_idx = all_alignment_idx[(from_data_set_idx, from_target_link.effector_bone_name[0])]
                            elif prev_to_alignment and (to_data_set_idx, to_target_link.effector_bone_name[0]) in all_alignment_idx and \
                                    all_alignment_idx[(to_data_set_idx, to_target_link.effector_bone_name[0])] >= 0:
                                # FROMが前回위치 맞춤OFFで、前回TOがONの場合、TOに寄せる
                                alignment_idx = all_alignment_idx[(to_data_set_idx, to_target_link.effector_bone_name[0])]
                            # elif (prev_floor_left_alignment or now_floor_left_alignment) and (to_data_set_idx, -1) in all_alignment_idx \
                            #         and all_alignment_idx[(to_data_set_idx, -1)] >= 0 and is_sit:
                            #     # 前回の左床위치 맞춤がONの場合、左に寄せる
                            #     alignment_idx = all_alignment_idx[(to_data_set_idx, -1)]
                            # elif (prev_floor_right_alignment or now_floor_right_alignment) and (to_data_set_idx, -2) in all_alignment_idx \
                            #         and all_alignment_idx[(to_data_set_idx, -2)] >= 0 and is_sit:
                            #     # 前回の右床위치 맞춤がONの場合、右に寄せる
                            #     alignment_idx = all_alignment_idx[(to_data_set_idx, -2)]
                            elif not prev_from_alignment and not prev_to_alignment and (to_alignment_idx >= 0 or (to_alignment_idx < 0 and is_sit)):
                                # FROMもTOも前回위치 맞춤OFFの場合、新たに発行
                                all_alignment_group_list.append({
                                    "fnos": [], "alignment_idxs": {}, "org_fno_global_effector": {}, \
                                    "org_mean_vec": {}, "org_origin_matrix": {}, "rep_fno_global_effector": {}, \
                                    "rep_fno_trunk_matrix": {}, "rep_fno_fileset_ratio": {}, "rep_block_fileset_ratio": [], \
                                    "org_effector_matrix": {}, "org_local_tip": {}
                                })
                                alignment_idx = len(all_alignment_group_list) - 1

                                # 위치 맞춤IDXを設定
                                all_alignment_idx[(from_data_set_idx, from_target_link.effector_bone_name[0])] = alignment_idx
                                all_alignment_idx[(to_data_set_idx, to_target_link.effector_bone_name[0])] = alignment_idx
                            else:
                                # 条件に合致しない場合、対象外
                                continue

                            # fno
                            if fno not in all_alignment_group_list[alignment_idx]["fnos"]:
                                all_alignment_group_list[alignment_idx]["fnos"].append(fno)

                            # 方向
                            # キーフレ単位の情報（1-2, 2-3 とかあるので、同じキーフレに複数の情報の可能性あり）
                            if fno not in all_alignment_group_list[alignment_idx]["alignment_idxs"]:
                                all_alignment_group_list[alignment_idx]["alignment_idxs"][fno] = []

                            if (from_data_set_idx, from_alignment_idx) not in all_alignment_group_list[alignment_idx]["alignment_idxs"][fno]:
                                all_alignment_group_list[alignment_idx]["alignment_idxs"][fno].append((from_data_set_idx, from_alignment_idx))

                            if (to_data_set_idx, to_alignment_idx) not in all_alignment_group_list[alignment_idx]["alignment_idxs"][fno]:
                                all_alignment_group_list[alignment_idx]["alignment_idxs"][fno].append((to_data_set_idx, to_alignment_idx))

                            # キーフレ単位のエフェクタ位置情報
                            if fno not in all_alignment_group_list[alignment_idx]["org_fno_global_effector"]:
                                all_alignment_group_list[alignment_idx]["org_fno_global_effector"][fno] = {}

                            all_alignment_group_list[alignment_idx]["org_fno_global_effector"][fno][(from_data_set_idx, from_alignment_idx)] \
                                = all_org_global_effector_vec[fno][(from_data_set_idx, from_alignment_idx)].data()

                            all_alignment_group_list[alignment_idx]["org_fno_global_effector"][fno][(to_data_set_idx, to_alignment_idx)] \
                                = all_org_global_effector_vec[fno][(to_data_set_idx, to_alignment_idx)].data()

                            # # ブロック単位のエフェクタ位置情報（とりあえず全部まとめて）
                            # all_alignment_group_list[alignment_idx]["org_block_global_effector"].append(\
                            #     all_org_global_effector_vec[fno][(from_data_set_idx, from_alignment_idx)].data())
                            # all_alignment_group_list[alignment_idx]["org_block_global_effector"].append(\
                            #     all_org_global_effector_vec[fno][(to_data_set_idx, to_alignment_idx)].data())

                            # 各キーフレにおける距離情報保持
                            if fno not in all_messages:
                                all_messages[fno] = []

                            # ログ用情報保持
                            all_messages[fno].append("○근접 있음: f: {0}({1}-{2}:{3}-{4}), 경계: {5}".format(fno, \
                                                     (from_data_set_idx + 1), from_target_link.effector_display_bone_name, \
                                                     (to_data_set_idx + 1), to_target_link.effector_display_bone_name, round(distance_ratio, 5)))

                            # 対象である場合、一旦登録
                            for ik_links in from_target_link.ik_links_list:
                                for link_name in ik_links.all().keys():
                                    bf = from_data_set.motion.calc_bf(link_name, fno)
                                    logger.test("f: %s(%s:%s), 초회 확정 now[%s], org[%s]", fno, (from_data_set_idx + 1), link_name, bf.rotation.toEulerAngles().to_log(), \
                                                bf.org_rotation.toEulerAngles().to_log())
                                    bf.org_rotation = bf.rotation.copy()
                                    from_data_set.motion.regist_bf(bf, link_name, fno)

                            for ik_links in to_target_link.ik_links_list:
                                for link_name in ik_links.all().keys():
                                    bf = to_data_set.motion.calc_bf(link_name, fno)
                                    logger.test("f: %s(%s:%s), 초회 확정 now[%s], org[%s]", fno, (to_data_set_idx + 1), link_name, bf.rotation.toEulerAngles().to_log(), \
                                                bf.org_rotation.toEulerAngles().to_log())
                                    bf.org_rotation = bf.rotation.copy()
                                    to_data_set.motion.regist_bf(bf, link_name, fno)
                            break
                        else:
                            if base_distance < distance_ratio <= base_distance * 3:
                                # 基準距離に近い場合、情報だけ保持
                                # 各キーフレにおける距離情報保持
                                if fno not in all_messages:
                                    all_messages[fno] = []

                                # ログ用情報保持
                                all_messages[fno].append("- 근접 없음: f: {0}({1}-{2}:{3}-{4}), 경계: {5}".format(fno, \
                                                         (from_data_set_idx + 1), from_target_link.effector_display_bone_name, \
                                                         (to_data_set_idx + 1), to_target_link.effector_display_bone_name, round(distance_ratio, 5)))

                if is_alignment_by_priority:
                    # 前の優先順位で既に위치 맞춤が発生している場合、終了
                    break

            if fno // 500 > prev_block_fno:
                logger.count("위치 맞춤 준비③", fno, fnos)
                prev_block_fno = fno // 500

        logger.count("위치 맞춤 준비③", fno, fnos)

        prev_block_fno = 0

        # グループ単位で中央値
        for group_idx, all_alignment_group in enumerate(all_alignment_group_list):
            # # ブロック単位の中央値
            # org_block_mean_vec = MVector3D(np.mean(all_alignment_group["org_block_global_effector"], axis=0))

            logger.debug("group_idx: %s, fnos: %s, alignment_idxs: %s", group_idx, all_alignment_group["fnos"], \
                         [all_alignment_group["alignment_idxs"][fno] for fno in all_alignment_group["fnos"]])

            for fno in all_alignment_group["fnos"]:
                # キーフレ単位の中央値
                org_fno_mean_vec = MVector3D(np.mean(list(all_alignment_group["org_fno_global_effector"][fno].values()), axis=0))

                # 床との위치 맞춤がある場合、TRUE
                is_floor = ([ai < 0 for (di, ai) in all_alignment_group["alignment_idxs"][fno]].count(True) > 0)

                # キーフレ単位の床位置
                if is_floor:
                    org_fno_mean_vec.setY(MVector3D(np.min(list(all_alignment_group["org_fno_global_effector"][fno].values()), axis=0)).y())

                for data_set_idx, alignment_idx in all_alignment_group["alignment_idxs"][fno]:
                    # 処理対象データセット
                    data_set = self.options.data_set_list[data_set_idx]
                    # 処理対象
                    target_link = self.target_links[data_set_idx][alignment_idx]

                    # 首根元（体幹の最終的な向き）までの行列
                    org_trunk_matrix = all_org_global_trunk_matrixs[fno][(data_set_idx, alignment_idx)].copy()

                    # エフェクタのグローバル位置
                    org_global_effector = all_org_global_effector_vec[fno][(data_set_idx, alignment_idx)]

                    # 体幹から見たキーフレ中央値のローカル位置
                    org_trunk_local_fno_origin = org_trunk_matrix.inverted() * org_fno_mean_vec

                    # # 体幹から見たブロック中央値のローカル位置
                    # org_trunk_local_block_origin = org_trunk_matrix.inverted() * org_block_mean_vec

                    # # ローカルYはブロック中央値を採用
                    # org_trunk_local_fno_origin.setY(org_trunk_local_block_origin.y())

                    # 作成元中点のローカル座標系
                    org_origin_matrix = org_trunk_matrix.copy()

                    # 作成元中点のローカル座標とする
                    org_origin_matrix.translate(org_trunk_local_fno_origin)

                    # 再生成した元中央値
                    org_mean_vec = MVector3D(org_trunk_matrix * org_trunk_local_fno_origin)

                    if target_link.tip_ik_links:
                        # 指先のグローバル位置
                        org_global_tip = all_org_global_tip_vec[fno][(data_set_idx, alignment_idx)]

                        # 体幹から見たエフェクタ（手首）のローカル位置
                        org_trunk_local_fno_effector = org_trunk_matrix.inverted() * org_global_effector

                        # 作成元エフェクタのローカル座標系
                        org_effector_matrix = org_trunk_matrix.copy()

                        # 作成元エフェクタのローカル座標とする
                        org_effector_matrix.translate(org_trunk_local_fno_effector)

                        # 指先のエフェクタ座標系から見たローカル位置
                        org_local_tip = org_effector_matrix.inverted() * org_global_tip

                        all_alignment_group["org_local_tip"][(fno, data_set_idx, alignment_idx)] = org_local_tip
                        all_alignment_group["org_effector_matrix"][(fno, data_set_idx, alignment_idx)] = org_effector_matrix

                    all_alignment_group["org_mean_vec"][(fno, data_set_idx, alignment_idx)] = org_mean_vec
                    all_alignment_group["org_origin_matrix"][(fno, data_set_idx, alignment_idx)] = org_origin_matrix

                    # # 作成元の中心点 ---------------
                    # debug_bone_name = "左1"

                    # debug_bf = VmdBoneFrame(fno)
                    # debug_bf.key = True
                    # debug_bf.set_name(debug_bone_name)
                    # debug_bf.position = org_mean_vec

                    # if debug_bone_name not in data_set.motion.bones:
                    #     data_set.motion.bones[debug_bone_name] = {}

                    # data_set.motion.bones[debug_bone_name][fno] = debug_bf

                    # # 作成元のエフェクタボーン位置 -------------
                    # debug_bone_name = "{0}2".format(target_link.effector_bone_name[0])

                    # debug_bf = VmdBoneFrame(fno)
                    # debug_bf.key = True
                    # debug_bf.set_name(debug_bone_name)
                    # debug_bf.position = org_global_effector

                    # if debug_bone_name not in data_set.motion.bones:
                    #     data_set.motion.bones[debug_bone_name] = {}

                    # data_set.motion.bones[debug_bone_name][fno] = debug_bf

            if fno // 500 > prev_block_fno:
                logger.count("위치 맞춤 준비④", fno, fnos)
                prev_block_fno = fno // 500

        logger.count("위치 맞춤 준비④", fno, fnos)

        return all_alignment_group_list, all_messages

    # 위치 맞춤실행
    cdef execute_alignment(self, list fnos, list all_alignment_group_list, dict all_messages, list bone_names):
        cdef int data_set_idx, alignment_idx, fidx, fno, ik_cnt, next_success_fno, now_ik_max_count, prev_block_fno, prev_fno, prev_success_fno
        cdef str bone_name, link_name
        cdef list group_data_set_idxs, next_fnos, next_success_fnos, overwrited, prev_success_fnos, is_success
        cdef dict aligned_rep_global_3ds, all_alignment_group
        cdef dict dot_far_limit_dict, dot_near_dict, dot_near_limit_dict, dot_start_dict, org_bfs, rep_global_3ds, rep_global_matrixs, results, start_org_bfs
        cdef bint is_avoidance_elbow_x, is_avoidance_arm_x, is_floor, is_multi
        cdef VmdBoneFrame bf, ik_bf, next_bf, prev_bf
        cdef MQuaternion correct_qq
        cdef MOptionsDataSet data_set
        cdef BoneLinks ik_links, now_ik_links
        cdef Bone link_bone
        cdef MVector3D org_fno_global_effector, org_local_effector, org_local_tip, prev_rep_diff, rep_diff, rep_effector_vec, rep_fno_mean_vec, rep_global_effector, aligned_rep_effector_vec
        cdef MVector3D rep_global_tip, rep_local_effector, rep_local_origin, rep_local_tip, rep_target_global_tip, rep_trunk_local_fno_effector, rep_trunk_local_fno_origin
        cdef MMatrix4x4 org_origin_matrix, rep_effector_matrix, rep_origin_matrix, rep_trunk_matrix
        cdef ArmAlignmentOption target_link

        fno = 0
        prev_block_fno = 0
        for all_alignment_group in all_alignment_group_list:
            group_data_set_idxs = []
            logger.debug("■그룹 전환 -------------------")

            for fno in all_alignment_group["fnos"]:
                for data_set_idx, alignment_idx in all_alignment_group["alignment_idxs"][fno]:
                    # 処理対象データセット
                    data_set = self.options.data_set_list[data_set_idx]
                    # 処理対象
                    target_link = self.target_links[data_set_idx][alignment_idx]

                    if (data_set_idx, alignment_idx) not in group_data_set_idxs:
                        # 処理対象セットを保持
                        group_data_set_idxs.append((data_set_idx, alignment_idx))

                    # 先モデルのそれぞれのグローバル位置
                    rep_global_3ds, rep_global_matrixs = \
                        MServiceUtils.c_calc_global_pos(data_set.rep_model, target_link.rep_links, data_set.motion, fno, return_matrix=True, is_local_x=True, limit_links=None)

                    # キーフレ単位のエフェクタ位置情報
                    if fno not in all_alignment_group["rep_fno_global_effector"]:
                        all_alignment_group["rep_fno_global_effector"][fno] = {}
                    all_alignment_group["rep_fno_global_effector"][fno][(data_set_idx, alignment_idx)] = rep_global_3ds[target_link.effector_bone_name].data()

                    if fno not in all_alignment_group["rep_fno_fileset_ratio"]:
                        all_alignment_group["rep_fno_fileset_ratio"][fno] = {}
                    all_alignment_group["rep_fno_fileset_ratio"][fno][(data_set_idx, alignment_idx)] = data_set.original_xz_ratio

                    # キーフレ単位の体幹座標系情報
                    if fno not in all_alignment_group["rep_fno_trunk_matrix"]:
                        all_alignment_group["rep_fno_trunk_matrix"][fno] = {}
                    all_alignment_group["rep_fno_trunk_matrix"][fno][(data_set_idx, alignment_idx)] = rep_global_matrixs["首根元"]

                    # 一度全部キーを追加する（キー自体は無効化のまま）
                    for bone_name in ["{0}腕".format(target_link.effector_bone_name[0]), "{0}ひじ".format(target_link.effector_bone_name[0])]:
                        if bone_name not in data_set.motion.bones:
                            data_set.motion.bones[bone_name] = {}
                        data_set.motion.bones[bone_name][fno] = data_set.motion.calc_bf(bone_name, fno)

            results = {}
            for fidx, fno in enumerate(all_alignment_group["fnos"]):
                if fno in all_messages.keys():
                    # 위치 맞춤メッセージ出力
                    [logger.info(msg) for msg in all_messages[fno]]

                # 床との위치 맞춤がある場合、TRUE
                is_floor = ([ai < 0 for (di, ai) in all_alignment_group["alignment_idxs"][fno]].count(True) > 0)
                # 他データとの위치 맞춤（床との組合せは除く）がある場合、TRUE
                is_multi = len(set([di for (di, ai) in all_alignment_group["alignment_idxs"][fno]])) > 1 and not is_floor

                # キーフレ単位の中央値
                rep_fno_mean_vec = MVector3D(np.mean(list(all_alignment_group["rep_fno_global_effector"][fno].values()), axis=0))
                # rep_fno_mean_vec = MVector3D(np.average(list(all_alignment_group["rep_fno_global_effector"][fno].values()), \
                #                                         weights=list(all_alignment_group["rep_fno_fileset_ratio"][fno].values()), axis=0))

                # キーフレ単位の床位置
                if is_floor:
                    rep_fno_mean_vec.setY(MVector3D(np.min(list(all_alignment_group["org_fno_global_effector"][fno].values()), axis=0)).y())

                for data_set_idx, alignment_idx in all_alignment_group["alignment_idxs"][fno]:
                    if alignment_idx < 0:
                        continue

                    # 処理対象データセット
                    data_set = self.options.data_set_list[data_set_idx]
                    # 処理対象
                    target_link = self.target_links[data_set_idx][alignment_idx]

                    # 首根先（体幹の最終的な向き）までの行列
                    rep_trunk_matrix = all_alignment_group["rep_fno_trunk_matrix"][fno][(data_set_idx, alignment_idx)].copy()

                    # # エフェクタのグローバル位置
                    # rep_global_effector = all_alignment_group["rep_fno_global_effector"]

                    # 体幹から見たキーフレ中央値のローカル位置
                    rep_trunk_local_fno_origin = rep_trunk_matrix.inverted() * rep_fno_mean_vec

                    # # 体幹から見たブロック中央値のローカル位置
                    # rep_trunk_local_block_origin = rep_trunk_matrix.inverted() * rep_block_mean_vec

                    # # ローカルYだけブロック中央値を採用
                    # rep_trunk_local_fno_origin.setY(rep_trunk_local_block_origin.y())

                    # 変換先中点のローカル座標系
                    rep_origin_matrix = rep_trunk_matrix.copy()

                    # 変換先中点のローカル座標とする
                    rep_origin_matrix.translate(rep_trunk_local_fno_origin)

                    # # 再生成した先中央値
                    # rep_mean_vec = MVector3D(rep_trunk_matrix * rep_trunk_local_fno_origin)

                    # 現在のエフェクタ位置
                    rep_effector_vec = MVector3D(all_alignment_group["rep_fno_global_effector"][fno][(data_set_idx, alignment_idx)])

                    # # 変換先の中心点 ---------------
                    # debug_bone_name = "右1"

                    # debug_bf = VmdBoneFrame(fno)
                    # debug_bf.key = True
                    # debug_bf.set_name(debug_bone_name)
                    # debug_bf.position = rep_mean_vec

                    # if debug_bone_name not in data_set.motion.bones:
                    #     data_set.motion.bones[debug_bone_name] = {}

                    # data_set.motion.bones[debug_bone_name][fno] = debug_bf

                    org_fno_global_effector = MVector3D(all_alignment_group["org_fno_global_effector"][fno][(data_set_idx, alignment_idx)])

                    # 作成元中点から見た、作成元エフェクタのローカル位置
                    org_origin_matrix = all_alignment_group["org_origin_matrix"][(fno, data_set_idx, alignment_idx)]
                    org_local_effector = org_origin_matrix.inverted() * org_fno_global_effector

                    logger.test("f: %s(%s:%s), org_origin[%s], org_fno_global_effector[%s]", fno, (data_set_idx + 1), \
                                target_link.effector_bone_name[0], (org_origin_matrix * MVector3D()).to_log(), \
                                org_fno_global_effector.to_log())

                    # 変換先エフェクタのローカル位置（作成元をコピー）
                    rep_local_effector = org_local_effector.copy()

                    # 変換先エフェクタの現在のローカル位置
                    rep_local_origin = rep_origin_matrix.inverted() * rep_fno_mean_vec

                    # ローカルエフェクタの位置調整
                    if is_multi:
                        # Xは小さい場合だけ体格差
                        if target_link.multi_ratio < 1:
                            rep_local_effector.setX(rep_local_effector.x() * target_link.multi_ratio)
                            rep_local_effector.setY(rep_local_effector.y() * target_link.multi_ratio)
                            rep_local_effector.setZ(rep_local_effector.z() * target_link.multi_ratio)

                        # # Yは体格差
                        # rep_local_effector.setY(rep_local_effector.y() * target_link.multi_ratio)
                        # # Zは調整なし
                    else:
                        # Xは全体の距離に対する割合(元々が近い場合は、変化量少なめ)
                        # rep_local_effector.setX(np.sin(rep_local_effector.x() / target_link.distance * np.pi) * target_link.ratio)

                        # Xは小さい子だけ体格差
                        if target_link.ratio < 1:
                            rep_local_effector.setX(rep_local_effector.x() * target_link.ratio)

                        # 床と合わせる場合、元のローカル位置のまま
                        if not is_floor:
                            # Yは体格差
                            rep_local_effector.setY(rep_local_effector.y() * target_link.ratio)
                            # Zは中点からの距離とする
                            rep_local_effector.setZ(rep_local_effector.z() + rep_local_origin.z())

                    logger.debug("f: %s(%s:%s), org_local_effector[%s], rep_trunk_local_fno_origin[%s], rep_local_effector[%s]", fno, (data_set_idx + 1), \
                                 target_link.effector_bone_name[0], org_local_effector.to_log(), rep_trunk_local_fno_origin.to_log(), rep_local_effector.to_log())

                    # 変換先エフェクタのグローバル位置
                    rep_global_effector = rep_origin_matrix * rep_local_effector

                    # # 変換先のエフェクタボーン位置 -------------
                    # debug_bone_name = "{0}3".format(target_link.effector_bone_name[0])

                    # debug_bf = VmdBoneFrame(fno)
                    # debug_bf.key = True
                    # debug_bf.set_name(debug_bone_name)
                    # debug_bf.position = rep_global_effector

                    # if debug_bone_name not in data_set.motion.bones:
                    #     data_set.motion.bones[debug_bone_name] = {}

                    # data_set.motion.bones[debug_bone_name][fno] = debug_bf

                    is_success = []

                    prev_rep_diff = MVector3D()

                    # 위치 맞춤前のbf情報
                    is_avoidance_arm_x = False
                    # ひじの回避有無
                    is_avoidance_elbow_x = False
                    org_bfs = {}
                    start_org_bfs = {}
                    for ik_links in target_link.ik_links_list:
                        for link_name in ik_links.all().keys():
                            if link_name not in org_bfs:
                                bf = data_set.motion.calc_bf(link_name, fno)
                                # bf.org_rotation = bf.rotation.copy()
                                # logger.debug("f: %s(%s:%s), org保持 now[%s], org[%s]", fno, (data_set_idx + 1), link_name, \
                                # bf.rotation.toEulerAngles().to_log(), bf.org_rotation.toEulerAngles().to_log())
                                # data_set.motion.regist_bf(bf, link_name, fno)

                                # 変位前の角度として保持
                                org_bfs[link_name] = bf.copy()
                                start_org_bfs[link_name] = bf.copy()

                                # 腕の回避が入っているか
                                is_avoidance_arm_x = is_avoidance_arm_x or (bf.avoidance == "x" and "腕" in link_name)
                                # ひじの回避Xが入っているか
                                is_avoidance_elbow_x = is_avoidance_elbow_x or (bf.avoidance == "x" and "ひじ" in link_name)

                    if is_avoidance_elbow_x:
                        logger.info("--팔꿈치 X 방향 회피 완료로 위치 맞춤 스킵: f:%s (%s-%s)", fno, (data_set_idx + 1), target_link.effector_display_bone_name)
                        continue

                    if is_avoidance_arm_x:
                        logger.info("--팔X방향 회피가 완료되어 팔꿈치 이후만 위치 맞춤: f:%s(%s-%s)", fno, (data_set_idx + 1), target_link.effector_display_bone_name)

                    # IK処理실행
                    for ik_cnt, (ik_links, ik_max_count) in enumerate(zip(target_link.ik_links_list, target_link.ik_count_list)):
                        if is_avoidance_arm_x:
                            # 腕X回避済みのため、除去
                            ik_links = ik_links.remove_links(["{0}腕".format(ik_links.first_name()[0]), "{0}腕捩".format(ik_links.first_name()[0])])
                        else:
                            elbow_bone_name = "{0}ひじ".format(ik_links.first_name()[0])

                            # ひじの角度が浅い場合、ひじ対象外とする
                            if elbow_bone_name in org_bfs and org_bfs[elbow_bone_name].org_rotation.toDegree() < 30:
                                ik_links = ik_links.remove_links([elbow_bone_name])

                        for now_ik_max_count in range(1):
                            now_ik_links = ik_links     # .from_links(target_bone_names[-1])
                            # if ik_cnt > 0:
                            #     for link_name, link_bone in now_ik_links.all().items():
                            #         link_bone.degree_limit = 3

                            logger.debug("IK計算開始(%s): f: %s(%s:%s), 現在[%s], 지정[%s]", now_ik_max_count, fno, (data_set_idx + 1), \
                                         list(now_ik_links.all().keys()), rep_effector_vec.to_log(), rep_global_effector.to_log())

                            # IK計算실행
                            MServiceUtils.c_calc_IK(data_set.rep_model, target_link.rep_links, data_set.motion, fno, rep_global_effector, now_ik_links, max_count=(ik_max_count + 1))

                            # 現在のエフェクタ位置
                            (aligned_rep_global_3ds, _) = MServiceUtils.c_calc_global_pos(data_set.rep_model, target_link.rep_links, data_set.motion, fno, return_matrix=False, is_local_x=False, limit_links=None)
                            aligned_rep_effector_vec = aligned_rep_global_3ds[target_link.effector_bone_name]

                            # 現在のエフェクタ位置との差分(エフェクタ位置が지정されている場合のみ)
                            rep_diff = rep_global_effector - aligned_rep_effector_vec

                            # IKの関連ボーンの内積チェック(処理前のbfと比較)
                            dot_near_dict = {}
                            dot_start_dict = {}
                            dot_near_limit_dict = {}
                            dot_far_limit_dict = {}
                            for link_name, link_bone in now_ik_links.all().items():
                                prev_fno, _ = data_set.motion.get_bone_prev_next_fno(link_name, fno=fno, start_fno=all_alignment_group["fnos"][0])

                                if 0 <= prev_fno and fno - prev_fno <= 1:
                                    # 近く前のキーフレがある場合、そのキーフレの最終的な角度を取得
                                    prev_bf = data_set.motion.calc_bf(link_name, prev_fno)
                                    # 変化量は小さめ
                                    dot_near_limit_dict[link_name] = link_bone.dot_near_limit if is_multi else link_bone.dot_single_limit
                                else:
                                    # 前のキーフレがない場合、変化前の角度とする
                                    prev_bf = start_org_bfs[link_name]
                                    # 変化量は多め
                                    dot_near_limit_dict[link_name] = link_bone.dot_far_limit if is_multi else link_bone.dot_single_limit

                                bf = data_set.motion.calc_bf(link_name, fno)
                                dot_near_dict[link_name] = MQuaternion.dotProduct(prev_bf.rotation, bf.rotation)
                                dot_start_dict[link_name] = MQuaternion.dotProduct(start_org_bfs[link_name].rotation, bf.rotation)
                                dot_far_limit_dict[link_name] = link_bone.dot_far_limit if is_multi else link_bone.dot_single_limit

                            # どちらにせよ一旦bf確定
                            for link_name, link_bone in now_ik_links.all().items():
                                ik_bf = data_set.motion.calc_bf(link_name, fno)
                                logger.test("f: %s(%s:%s), 일단 확정 now[%s], org[%s]", fno, (data_set_idx + 1), link_name, ik_bf.rotation.toEulerAngles().to_log(), \
                                            ik_bf.org_rotation.toEulerAngles().to_log())
                                data_set.motion.regist_bf(ik_bf, link_name, fno)

                            if (prev_rep_diff == MVector3D() or np.sum(np.abs(rep_diff.data())) < np.sum(np.abs(prev_rep_diff.data()))) and \
                                    np.count_nonzero(np.where(np.abs(rep_diff.data()) > (0.2 if data_set.original_xz_ratio > 0.5 else 0.1), 1, 0)) == 0:
                                logger.debug("☆위치맞춤 실행성공(%s): f:%s(%s:%s), 지정[%s], 결과[%s], diff[%s], dot_near_dict: [%s], dot_start_dict: [%s], org: [%s], now_vec: [%s]", \
                                                now_ik_max_count, fno, (data_set_idx + 1), list(now_ik_links.all().keys()), rep_global_effector.to_log(), \
                                                aligned_rep_effector_vec.to_log(), rep_diff.to_log(), list(dot_near_dict.values()), list(dot_start_dict.values()), \
                                                start_org_bfs[link_name].rotation.toEulerAngles().to_log(), bf.rotation.toEulerAngles().to_log())

                                # # 위치 맞춤後のエフェクタボーン位置 -------------
                                # debug_bone_name = "{0}4".format(target_link.effector_bone_name[0])

                                # debug_bf = VmdBoneFrame(fno)
                                # debug_bf.key = True
                                # debug_bf.set_name(debug_bone_name)
                                # debug_bf.position = aligned_rep_effector_vec

                                # if debug_bone_name not in data_set.motion.bones:
                                #     data_set.motion.bones[debug_bone_name] = {}

                                # data_set.motion.bones[debug_bone_name][fno] = debug_bf
                                # # ----------

                                # 大体同じ位置にあって、角度もそう大きくズレてない場合、OK(全部上書き)
                                is_success = [True]

                                # org保持し直す
                                for link_name in now_ik_links.all().keys():
                                    org_bfs[link_name].rotation = data_set.motion.calc_bf(link_name, fno).rotation.copy()

                                # 前回とまったく同じ場合か、充分に近い場合、IK的に動きがないので終了
                                if prev_rep_diff == rep_diff or np.count_nonzero(np.where(np.abs(rep_diff.data()) > 0.05, 1, 0)) == 0:
                                    break

                                prev_rep_diff = rep_diff

                            elif (prev_rep_diff == MVector3D() or (prev_rep_diff != MVector3D() and np.sum(np.abs(rep_diff.data())) < np.sum(np.abs(prev_rep_diff.data())))) and \
                                    (np.count_nonzero(np.where(np.abs(rep_diff.data()) > (0.7 if data_set.original_xz_ratio > 0.5 else 0.3), 1, 0)) == 0):

                                logger.debug("☆위치 맞춤 실행 약간 실패 채용(%s): f:%s(%s:%s), 지정[%s], 결과[%s], diff[%s], dot_near_dict: [%s], dot_start_dict: [%s], org_vec: [%s], now_vec: [%s]", \
                                                now_ik_max_count, fno, (data_set_idx + 1), list(now_ik_links.all().keys()), rep_global_effector.to_log(), \
                                                aligned_rep_effector_vec.to_log(), rep_diff.to_log(), list(dot_near_dict.values()), list(dot_start_dict.values()), \
                                                start_org_bfs[link_name].rotation.toEulerAngles().to_log(), bf.rotation.toEulerAngles().to_log())

                                # 採用されたらOK
                                is_success.append(True)

                                # # 위치 맞춤後のエフェクタボーン位置 -------------
                                # debug_bone_name = "{0}4".format(target_link.effector_bone_name[0])

                                # debug_bf = VmdBoneFrame(fno)
                                # debug_bf.key = True
                                # debug_bf.set_name(debug_bone_name)
                                # debug_bf.position = aligned_rep_effector_vec

                                # if debug_bone_name not in data_set.motion.bones:
                                #     data_set.motion.bones[debug_bone_name] = {}

                                # data_set.motion.bones[debug_bone_name][fno] = debug_bf
                                # # ----------

                                # ちょっと실패初回か、前回より差が小さくなってる場合、org_bfを保持し直して、もう一周試す
                                for link_name in now_ik_links.all().keys():
                                    org_bfs[link_name].rotation = data_set.motion.calc_bf(link_name, fno).rotation.copy()

                                # 前回とまったく同じ場合か、充分に近い場合、IK的に動きがないので終了
                                if prev_rep_diff == rep_diff or np.count_nonzero(np.where(np.abs(rep_diff.data()) > 0.05, 1, 0)) == 0:
                                    break

                                prev_rep_diff = rep_diff
                            else:
                                logger.debug("★위치맞춤 실행 약간 실패 불채택(%s): f:%s(%s:%s), 지정[%s], 결과[%s], diff[%s], dot_near_dict: [%s], dot_start_dict: [%s], org_vec: [%s], now_vec: [%s]", \
                                                now_ik_max_count, fno, (data_set_idx + 1), list(now_ik_links.all().keys()), rep_global_effector.to_log(), \
                                                aligned_rep_effector_vec.to_log(), rep_diff.to_log(), list(dot_near_dict.values()), list(dot_start_dict.values()), \
                                                start_org_bfs[link_name].rotation.toEulerAngles().to_log(), bf.rotation.toEulerAngles().to_log())

                                is_success.append(False)

                                if prev_rep_diff == MVector3D():
                                    # 初回실패の場合、とりあえず設定
                                    prev_rep_diff = rep_diff

                        if is_success == [True]:
                            # 성공していたらそのまま終了
                            break

                    if len(is_success) > 0:
                        if is_success.count(True) == 0:
                            # 全てのパターンで실패してる場合、실패ログ
                            logger.info("× 위치 맞춤 실패: f: %s(%s-%s)", fno, (data_set_idx + 1), target_link.effector_display_bone_name)

                            # 실패記録
                            results[(fno, data_set_idx, alignment_idx)] = False

                        else:
                            # 성공記録
                            results[(fno, data_set_idx, alignment_idx)] = True

                            # どっか성공していたら、最後に성공したトコまで戻す
                            for link_name in list(now_ik_links.all().keys())[1:]:
                                data_set.motion.regist_bf(org_bfs[link_name].copy(), link_name, fno)

                            if len(is_success) > 1 and is_success.count(False) > 0:
                                # どこかのパターンで실패している場合、일부성공ログ
                                logger.info("△위치 맞춤 일부 성공: f: %s(%s-%s)", fno, (data_set_idx + 1), target_link.effector_display_bone_name)
                            else:
                                # 全部성공している場合、성공ログ
                                logger.info("○ 위치 맞춤 성공: f: %s(%s-%s)", fno, (data_set_idx + 1), target_link.effector_display_bone_name)

            # 결과チェック
            for fidx, fno in enumerate(all_alignment_group["fnos"]):

                # 床との위치 맞춤がある場合、TRUE
                is_floor = ([ai < 0 for (di, ai) in all_alignment_group["alignment_idxs"][fno]].count(True) > 0)
                # 他データとの위치 맞춤（床との組合せは除く）がある場合、TRUE
                is_multi = len(set([di for (di, ai) in all_alignment_group["alignment_idxs"][fno]])) > 1 and not is_floor

                for data_set_idx, alignment_idx in all_alignment_group["alignment_idxs"][fno]:
                    if (fno, data_set_idx, alignment_idx) in results and not results[(fno, data_set_idx, alignment_idx)]:
                        # 위치 맞춤に실패した場合

                        # 処理対象データセット
                        data_set = self.options.data_set_list[data_set_idx]
                        # 処理対象
                        target_link = self.target_links[data_set_idx][alignment_idx]

                        overwrited = []
                        for ik_links in target_link.ik_links_list:
                            for link_name in list(ik_links.all().keys())[1:]:
                                # まだ該当リンクの上書き処理が終わってない場合
                                if link_name not in overwrited:
                                    overwrited.append(link_name)

                                    # 지정したキーフレより前後のキーフレ
                                    prev_fnos = data_set.motion.get_bone_fnos(link_name, start_fno=all_alignment_group["fnos"][0], end_fno=fno - 1)
                                    next_fnos = data_set.motion.get_bone_fnos(link_name, start_fno=fno + 1, end_fno=all_alignment_group["fnos"][-1])

                                    # 前回성공したキーフレ群
                                    prev_success_fnos = [fno for fno in prev_fnos if (fno, data_set_idx, alignment_idx) in results and results[(fno, data_set_idx, alignment_idx)]]

                                    logger.test("f: %s, (%s:%s), prev_fnos: %s, data: %s, prev_success: %s", fno, (data_set_idx + 1), link_name, prev_fnos, \
                                                [results[(fno, data_set_idx, alignment_idx)] for fno in reversed(prev_fnos) if (fno, data_set_idx, alignment_idx) in results], prev_success_fnos)

                                    if len(prev_success_fnos) == 0:
                                        # 前回성공したキーフレがグループの中に見つからない場合、グループ内の最初のキーフレの可能性がある
                                        prev_success_fno = -1
                                    else:
                                        # 見つかった場合は、そのキーフレ群の最後（直近）
                                        prev_success_fno = prev_success_fnos[-1]

                                    # 次に성공したキーフレ群
                                    next_success_fnos = [fno for fno in next_fnos if (fno, data_set_idx, alignment_idx) in results and results[(fno, data_set_idx, alignment_idx)]]

                                    logger.debug("f: %s, (%s:%s), next_fnos: %s, data: %s, next_success: %s", fno, (data_set_idx + 1), link_name, next_fnos, \
                                                 [results[(fno, data_set_idx, alignment_idx)] for fno in reversed(next_fnos) if (fno, data_set_idx, alignment_idx) in results], next_success_fnos)

                                    if len(next_success_fnos) == 0:
                                        # 次に성공したキーフレがグループの中に見つからない場合、グループ内の最後のキーフレの可能性がある
                                        next_success_fno = -1
                                    else:
                                        # 見つかった場合は、そのキーフレ群の最後（直近）
                                        next_success_fno = next_success_fnos[0]

                                    bf = data_set.motion.calc_bf(link_name, fno)
                                    if prev_success_fno < 0 or next_success_fno < 0 or fno - prev_success_fno <= 2 or next_success_fno - fno <= 2:

                                        # 前後どちらか取れなかった場合、もしくは離れている場合、初期状態に戻す
                                        if prev_success_fno > 0 and fno - prev_success_fno <= 2:
                                            # 前の성공キーフレがあり、かつ近いの場合、前のキーフレを適用する
                                            prev_bf = data_set.motion.calc_bf(link_name, prev_success_fno)

                                            logger.debug("f: %s, (%s:%s), pfno: %s, nfno: %s, 실패 덮어쓰기(전) start now[%s], prev[%s]", fno, (data_set_idx + 1), link_name, \
                                                         prev_success_fno, next_success_fno, bf.rotation.toEulerAngles().to_log(), prev_bf.rotation.toEulerAngles().to_log())

                                            bf.rotation = prev_bf.rotation

                                            # 성공と見なす
                                            results[(fno, data_set_idx, alignment_idx)] = True
                                        elif next_success_fno > 0 and next_success_fno - fno <= 2:
                                            # 後の성공キーフレがあり、かつ近いの場合、後のキーフレを適用する
                                            next_bf = data_set.motion.calc_bf(link_name, next_success_fno)

                                            logger.debug("f: %s, (%s:%s), pfno: %s, nfno: %s, 실패 덮어쓰기(후) start now[%s], next[%s]", fno, (data_set_idx + 1), link_name, \
                                                         prev_success_fno, next_success_fno, bf.rotation.toEulerAngles().to_log(), next_bf.rotation.toEulerAngles().to_log())

                                            bf.rotation = next_bf.rotation

                                            # 성공と見なす
                                            results[(fno, data_set_idx, alignment_idx)] = True
                                        else:
                                            logger.debug("f: %s, (%s:%s), pfno: %s, nfno: %s, 실패 덮어쓰기(처음) start now[%s], org[%s]", fno, (data_set_idx + 1), link_name, \
                                                         prev_success_fno, next_success_fno, bf.rotation.toEulerAngles().to_log(), bf.org_rotation.toEulerAngles().to_log())

                                            bf.rotation = bf.org_rotation.copy()
                                        data_set.motion.regist_bf(bf, link_name, fno)
                                    else:
                                        prev_bf = data_set.motion.calc_bf(link_name, prev_success_fno)
                                        next_bf = data_set.motion.calc_bf(link_name, next_success_fno)

                                        # 前後どちらも取れた場合、そのslerpとする
                                        correct_qq = MQuaternion.slerp(prev_bf.rotation, next_bf.rotation, ((fno - prev_success_fno) / (next_success_fno - prev_success_fno)))

                                        logger.debug("f: %s, (%s:%s), pfno: %s, nfno: %s, 실패 덮어쓰기 slerp now[%s], correct[%s]", fno, (data_set_idx + 1), link_name, \
                                                     prev_success_fno, next_success_fno, bf.rotation.toEulerAngles().to_log(), correct_qq.toEulerAngles().to_log())

                                        bf.rotation = correct_qq
                                        data_set.motion.regist_bf(bf, link_name, fno)

                                        # 성공と見なす
                                        results[(fno, data_set_idx, alignment_idx)] = True

            # 指先위치 맞춤
            for fidx, fno in enumerate(all_alignment_group["fnos"]):

                # 床との위치 맞춤がある場合、TRUE
                is_floor = ([ai < 0 for (di, ai) in all_alignment_group["alignment_idxs"][fno]].count(True) > 0)
                # 他データとの위치 맞춤（床との組合せは除く）がある場合、TRUE
                is_multi = len(set([di for (di, ai) in all_alignment_group["alignment_idxs"][fno]])) > 1 and not is_floor

                for data_set_idx, alignment_idx in all_alignment_group["alignment_idxs"][fno]:
                    if (fno, data_set_idx, alignment_idx) not in results:
                        # 위치 맞춤そのものが성공していない場合、スルー
                        continue

                    # 処理対象データセット
                    data_set = self.options.data_set_list[data_set_idx]
                    # 処理対象
                    target_link = self.target_links[data_set_idx][alignment_idx]

                    if target_link.tip_ik_links:
                        # 指先合わせが必要な場合

                        is_success = []

                        prev_rep_diff = MVector3D()

                        # 위치 맞춤前のbf情報
                        org_bfs = {}
                        start_org_bfs = {}
                        for link_name in target_link.tip_ik_links.all().keys():
                            if link_name not in org_bfs:
                                bf = data_set.motion.calc_bf(link_name, fno)

                                # 変位前の角度として保持
                                org_bfs[link_name] = bf.copy()
                                start_org_bfs[link_name] = bf.copy()

                        # 先モデルのそれぞれのグローバル位置最新データ
                        rep_global_3ds, rep_global_matrixs = \
                            MServiceUtils.c_calc_global_pos(data_set.rep_model, target_link.rep_links, data_set.motion, fno, return_matrix=True, is_local_x=True, limit_links=None)

                        # 指先のローカル位置
                        org_local_tip = MVector3D(all_alignment_group["org_local_tip"][(fno, data_set_idx, alignment_idx)])

                        # 首根先（体幹の最終的な向き）までの行列
                        rep_effector_matrix = rep_global_matrixs["首根元"].copy()

                        # エフェクタのグローバル位置
                        rep_global_effector = rep_global_3ds[target_link.effector_bone_name]

                        # 体幹から見たキーフレ中央値のローカル位置
                        rep_trunk_local_fno_effector = rep_effector_matrix.inverted() * rep_global_effector

                        # 変換先エフェクタのローカル座標とする
                        rep_effector_matrix.translate(rep_trunk_local_fno_effector)

                        # 先モデルの指先座標系
                        rep_global_tip = rep_global_3ds[target_link.tip_bone_name]

                        # 変換先エフェクタから見た指先のローカル座標
                        rep_local_tip = rep_effector_matrix.inverted() * rep_global_tip

                        # ローカルのXを元に合わせる
                        rep_local_tip.setX(org_local_tip.x())
                        # rep_local_tip.setZ(org_local_tip.z())

                        # 目標とする指先の位置
                        rep_target_global_tip = rep_effector_matrix * rep_local_tip

                        # 끝부분ＩＫリンク
                        now_ik_links = target_link.tip_ik_links

                        # IK処理실행
                        for now_ik_max_count in range(1):
                            logger.debug("끝부분 IK 계산 개시(%s): f:%s(%s:%s), 현재 [%s], 지정[%s]", now_ik_max_count, fno, (data_set_idx + 1), \
                                         list(now_ik_links.all().keys()), rep_global_tip.to_log(), rep_target_global_tip.to_log())

                            # IK計算실행
                            MServiceUtils.c_calc_IK(data_set.rep_model, target_link.rep_links, data_set.motion, fno, rep_target_global_tip, now_ik_links, max_count=10)

                            # 現在のエフェクタ位置
                            aligned_rep_global_3ds, _ = MServiceUtils.c_calc_global_pos(data_set.rep_model, target_link.rep_links, data_set.motion, fno, return_matrix=False, is_local_x=False, limit_links=None)
                            aligned_rep_effector_vec = aligned_rep_global_3ds[target_link.tip_bone_name]

                            # 現在のエフェクタ位置との差分(エフェクタ位置が지정されている場合のみ)
                            rep_diff = rep_target_global_tip - aligned_rep_effector_vec

                            # IKの関連ボーンの内積チェック(処理前のbfと比較)
                            dot_near_dict = {}
                            dot_start_dict = {}
                            dot_near_limit_dict = {}
                            dot_far_limit_dict = {}
                            for link_name, link_bone in now_ik_links.all().items():
                                prev_fno, _ = data_set.motion.get_bone_prev_next_fno(link_name, fno=fno, start_fno=all_alignment_group["fnos"][0])

                                if 0 <= prev_fno and fno - prev_fno <= 1:
                                    # 近く前のキーフレがある場合、そのキーフレの最終的な角度を取得
                                    prev_bf = data_set.motion.calc_bf(link_name, prev_fno)
                                    # 変化量は小さめ
                                    dot_near_limit_dict[link_name] = link_bone.dot_near_limit if is_multi else link_bone.dot_single_limit
                                else:
                                    # 前のキーフレがない場合、変化前の角度とする
                                    prev_bf = start_org_bfs[link_name]
                                    # 変化量は多め
                                    dot_near_limit_dict[link_name] = link_bone.dot_far_limit if is_multi else link_bone.dot_single_limit

                                bf = data_set.motion.calc_bf(link_name, fno)
                                dot_near_dict[link_name] = MQuaternion.dotProduct(prev_bf.rotation, bf.rotation)
                                dot_start_dict[link_name] = MQuaternion.dotProduct(start_org_bfs[link_name].rotation, bf.rotation)
                                dot_far_limit_dict[link_name] = link_bone.dot_far_limit if is_multi else link_bone.dot_single_limit

                            # どちらにせよ一旦bf確定
                            for link_name, link_bone in now_ik_links.all().items():
                                ik_bf = data_set.motion.calc_bf(link_name, fno)
                                logger.test("f: %s(%s:%s), 일단 확정 now[%s], org[%s]", fno, (data_set_idx + 1), link_name, ik_bf.rotation.toEulerAngles().to_log(), \
                                            ik_bf.org_rotation.toEulerAngles().to_log())
                                data_set.motion.regist_bf(ik_bf, link_name, fno)

                            if np.count_nonzero(np.where(np.array(list(dot_near_dict.values())) < np.array(list(dot_near_limit_dict.values())), 1, 0)) == 0 and \
                                    np.count_nonzero(np.where(np.array(list(dot_start_dict.values())) < np.array(list(dot_far_limit_dict.values())), 1, 0)) == 0:
                                if (prev_rep_diff == MVector3D() or np.sum(np.abs(rep_diff.data())) < np.sum(np.abs(prev_rep_diff.data()))) and \
                                        np.count_nonzero(np.where(np.abs(rep_diff.data()) > 0.2 * data_set.original_xz_ratio, 1, 0)) == 0:
                                    logger.debug("☆끝부 분위치 맞춤 실행 성공(%s): f: %s(%s:%s), 지정[%s], 결과[%s], diff[%s], dot_near_dict: [%s], dot_start_dict: [%s], org: [%s], now_vec: [%s]", \
                                                 now_ik_max_count, fno, (data_set_idx + 1), list(now_ik_links.all().keys()), rep_target_global_tip.to_log(), \
                                                 aligned_rep_effector_vec.to_log(), rep_diff.to_log(), list(dot_near_dict.values()), list(dot_start_dict.values()), \
                                                 start_org_bfs[link_name].rotation.toEulerAngles().to_log(), bf.rotation.toEulerAngles().to_log())

                                    # 大体同じ位置にあって、角度もそう大きくズレてない場合、OK(全部上書き)
                                    is_success = [True]

                                    # org保持し直す
                                    for link_name in now_ik_links.all().keys():
                                        org_bfs[link_name].rotation = data_set.motion.calc_bf(link_name, fno).rotation.copy()

                                    # 前回とまったく同じ場合か、充分に近い場合、IK的に動きがないので終了
                                    if prev_rep_diff == rep_diff or np.count_nonzero(np.where(np.abs(rep_diff.data()) > 0.05, 1, 0)) == 0:
                                        break

                                    prev_rep_diff = rep_diff

                                elif (prev_rep_diff == MVector3D() or (prev_rep_diff != MVector3D() and np.sum(np.abs(rep_diff.data())) < np.sum(np.abs(prev_rep_diff.data())))) and \
                                        (np.count_nonzero(np.where(np.abs(rep_diff.data()) > 0.7 * data_set.original_xz_ratio, 1, 0)) == 0):

                                    logger.debug("☆끝부분 위치 맞춤 실행 조금 실패 채용(%s): f: %s(%s:%s), 지정[%s], 결과[%s], diff[%s], dot_near_dict: [%s], dot_start_dict: [%s], org_vec: [%s], now_vec: [%s]", \
                                                 now_ik_max_count, fno, (data_set_idx + 1), list(now_ik_links.all().keys()), rep_target_global_tip.to_log(), \
                                                 aligned_rep_effector_vec.to_log(), rep_diff.to_log(), list(dot_near_dict.values()), list(dot_start_dict.values()), \
                                                 start_org_bfs[link_name].rotation.toEulerAngles().to_log(), bf.rotation.toEulerAngles().to_log())

                                    # 採用されたらOK
                                    is_success.append(True)

                                    # ちょっと실패初回か、前回より差が小さくなってる場合、org_bfを保持し直して、もう一周試す
                                    for link_name in now_ik_links.all().keys():
                                        org_bfs[link_name].rotation = data_set.motion.calc_bf(link_name, fno).rotation.copy()

                                    prev_rep_diff = rep_diff
                                else:
                                    logger.debug("★끝부분 위치 맞춤 실행 조금 실패 불채용(%s): f: %s(%s:%s), 지정[%s], 결과[%s], diff[%s], dot_near_dict: [%s], dot_start_dict: [%s], org_vec: [%s], now_vec: [%s]", \
                                                 now_ik_max_count, fno, (data_set_idx + 1), list(now_ik_links.all().keys()), rep_target_global_tip.to_log(), \
                                                 aligned_rep_effector_vec.to_log(), rep_diff.to_log(), list(dot_near_dict.values()), list(dot_start_dict.values()), \
                                                 start_org_bfs[link_name].rotation.toEulerAngles().to_log(), bf.rotation.toEulerAngles().to_log())

                                    is_success.append(False)

                                    if prev_rep_diff == MVector3D():
                                        # 初回실패の場合、とりあえず設定
                                        prev_rep_diff = rep_diff
                            else:
                                logger.debug("★끝부분위치 맞춤 실행 실패(%s): f: %s(%s:%s), 지정[%s], 결과[%s], diff[%s], dot_near_dict: [%s], dot_start_dict: [%s], org_vec: [%s], now_vec: [%s]", \
                                             now_ik_max_count, fno, (data_set_idx + 1), list(now_ik_links.all().keys()), rep_target_global_tip.to_log(), \
                                             aligned_rep_effector_vec.to_log(), rep_diff.to_log(), list(dot_near_dict.values()), list(dot_start_dict.values()), \
                                             start_org_bfs[link_name].rotation.toEulerAngles().to_log(), bf.rotation.toEulerAngles().to_log())

                                is_success.append(False)

                        if len(is_success) > 0:
                            if is_success.count(True) == 0:
                                # 全てのパターンで실패してる場合、실패ログ
                                logger.info("× 끝부분 위치 맞춤 실패: f: %s(%s-%s)", fno, (data_set_idx + 1), target_link.effector_display_bone_name)

                                # 最初に戻す
                                for link_name in list(now_ik_links.all().keys())[1:]:
                                    data_set.motion.regist_bf(start_org_bfs[link_name].copy(), link_name, fno)
                            else:
                                # どっか성공していたら、最後に성공したトコまで戻す
                                for link_name in list(now_ik_links.all().keys())[1:]:
                                    data_set.motion.regist_bf(org_bfs[link_name].copy(), link_name, fno)

                                if len(is_success) > 1 and is_success.count(False) > 0:
                                    # どこかのパターンで실패している場合、일부성공ログ
                                    logger.info("△ 끝부분 위치 맞춤 일부 성공: f: %s(%s-%s)", fno, (data_set_idx + 1), target_link.effector_display_bone_name)
                                else:
                                    # 全部성공している場合、성공ログ
                                    logger.info("○ 끝부분 위치 맞춤 성공: f: %s(%s-%s)", fno, (data_set_idx + 1), target_link.effector_display_bone_name)

            if fno // 500 > prev_block_fno:
                logger.count("위치 맞춤", fno, fnos)
                prev_block_fno = fno // 500

        logger.count("위치 맞춤", fno, fnos)

    # 手首위치 맞춤の準備
    def prepare_wrist(self, data_set_idx: int):
        self.target_links[data_set_idx] = {}
        data_set = self.options.data_set_list[data_set_idx]

        bone_names = []

        for (alignment_idx, direction) in [(1, "左"), (2, "右")]:
            tip_bone_name = "{0}人指先実体".format(direction)
            if tip_bone_name not in data_set.org_model.bones or tip_bone_name not in data_set.rep_model.bones:
                # 指先がどっちかにない場合、手首を対象とする
                tip_bone_name = "{0}手首".format(direction)

            # 指先までのリンク
            org_wrist_links = data_set.org_model.create_link_2_top_one(tip_bone_name)
            rep_wrist_links = data_set.rep_model.create_link_2_top_one(tip_bone_name)

            # IK用リンク（エフェクタから追加していく）
            ik_links_list = []
            ik_count_list = []

            wrist_bone = rep_wrist_links.get("{0}手首".format(direction))

            # if f"{direction}手捩" in data_set.rep_model.bones and f"{direction}手捩" in data_set.motion.bones:
            #     wrist_twist_bone = rep_wrist_links.get("{0}手捩".format(direction))
            #     wrist_twist_bone.dot_near_limit = 0.97
            #     wrist_twist_bone.dot_far_limit = 0.8
            #     wrist_twist_bone.dot_single_limit = 0.9
            #     wrist_twist_bone.degree_limit = 57.2957

            elbow_bone = rep_wrist_links.get("{0}ひじ".format(direction))
            elbow_bone.dot_near_limit = 0.97
            elbow_bone.dot_far_limit = 0.7
            elbow_bone.dot_single_limit = 0.9
            elbow_bone.degree_limit = 57.2957

            # if f"{direction}腕捩" in data_set.rep_model.bones and f"{direction}腕捩" in data_set.motion.bones:
            #     arm_twist_bone = rep_wrist_links.get("{0}腕捩".format(direction))
            #     arm_twist_bone.dot_near_limit = 0.97
            #     arm_twist_bone.dot_far_limit = 0.8
            #     arm_twist_bone.dot_single_limit = 0.9
            #     arm_twist_bone.degree_limit = 57.2957

            arm_bone = rep_wrist_links.get("{0}腕".format(direction))
            arm_bone.dot_near_limit = 0.97
            arm_bone.dot_far_limit = 0.8
            arm_bone.dot_single_limit = 0.9
            arm_bone.degree_limit = 57.2957

            ik_links = BoneLinks()
            ik_links.append(wrist_bone)

            # if f"{direction}手捩" in data_set.rep_model.bones and f"{direction}手捩" in data_set.motion.bones:
            #     ik_links.append(wrist_twist_bone)

            ik_links.append(elbow_bone)

            # if f"{direction}腕捩" in data_set.rep_model.bones and f"{direction}腕捩" in data_set.motion.bones:
            #     ik_links.append(arm_twist_bone)

            ik_links.append(arm_bone)
            ik_links_list.append(ik_links)
            ik_count_list.append(50)

            if tip_bone_name == "{0}手首".format(direction):
                # 위치 맞춤が手首の場合、끝부분調整不要
                tip_ik_links = None
                # 手のひらの長さ（指のないモデルである場合、仮に1を設定）
                org_palm_length = 1
                rep_palm_length = 1
            else:
                tip_ik_links = BoneLinks()
                tip_ik_links.append(rep_wrist_links.get(tip_bone_name))
                tip_ik_links.append(rep_wrist_links.get("{0}手首".format(direction)))
                # 手のひらの長さ
                org_palm_length = (data_set.org_model.bones["{0}手首".format(direction)].position.distanceToPoint(data_set.org_model.bones[tip_bone_name].position))
                rep_palm_length = (data_set.rep_model.bones["{0}手首".format(direction)].position.distanceToPoint(data_set.rep_model.bones[tip_bone_name].position))

            logger.info("【No.%s】작성 원본 모델의 %s 손바닥 크기: %s", (data_set_idx + 1), direction, round(org_palm_length, 5))
            logger.info("【No.%s】변환용 모델의 %s 손바닥 크기: %s", (data_set_idx + 1), direction, round(rep_palm_length, 5))

            # 手首リンク登録
            self.target_links[data_set_idx][alignment_idx] = \
                ArmAlignmentOption(org_wrist_links, rep_wrist_links, ik_links_list, ik_count_list, tip_ik_links, \
                                   org_palm_length, rep_palm_length, data_set.org_model, data_set.rep_model, "{0}腕".format(direction), \
                                   "{0}手首".format(direction), "{0}手首".format(direction), tip_bone_name, self.options.arm_options.alignment_distance_wrist, data_set.xz_ratio, 1)

            # 腕・ひじのキーフレ
            bone_names.extend(["{0}腕".format(direction), "{0}腕捩".format(direction), "{0}ひじ".format(direction), "{0}手捩".format(direction), "{0}手首".format(direction)])

            # 床위치 맞춤も行う場合、リンク追加生成
            if self.options.arm_options.alignment_floor_flg:
                # IK用リンク（エフェクタから追加していく）
                ik_links_list = []
                ik_count_list = []

                ik_links = BoneLinks()
                ik_links.append(wrist_bone)

                if rep_wrist_links.get("上半身2") and "上半身2" in data_set.motion.bones:
                    # 上半身2もある場合、上半身2も補正する
                    upper_bone2 = rep_wrist_links.get("上半身2")
                    upper_bone2.dot_near_limit = 0.97
                    upper_bone2.dot_far_limit = 0.95
                    upper_bone2.dot_single_limit = 0.95
                    upper_bone2.degree_limit = 57.2957
                    ik_links.append(upper_bone2)

                upper_bone = rep_wrist_links.get("上半身")
                upper_bone.dot_near_limit = 0.97
                upper_bone.dot_far_limit = 0.95
                upper_bone.dot_single_limit = 0.95
                upper_bone.degree_limit = 57.2957
                ik_links.append(upper_bone)

                ik_links_list.append(ik_links)
                ik_count_list.append(30)

                # 手首リンク登録(alignmentをマイナスとする)
                self.target_links[data_set_idx][-alignment_idx] = \
                    ArmAlignmentOption(org_wrist_links, rep_wrist_links, ik_links_list, ik_count_list, tip_ik_links, \
                                       org_palm_length, rep_palm_length, data_set.org_model, data_set.rep_model, "床", \
                                       "{0}手首".format(direction), "床", tip_bone_name, \
                                       self.options.arm_options.alignment_distance_floor, data_set.xz_ratio, 2)

        if self.options.arm_options.alignment_floor_flg:
            # 床위치 맞춤の場合、上半身系も対象とする
            bone_names.extend(["上半身", "上半身2"])

        return bone_names

    # 指위치 맞춤の準備
    def prepare_finger(self, data_set_idx: int):
        data_set = self.options.data_set_list[data_set_idx]
        bone_names = []

        # ボーンセット確認
        finger_name_list = []
        for direction in ["左", "右"]:
            for finger_name in ["親指", "人指", "中指", "薬指", "小指"]:
                finger_name_list.append("{0}{1}先実体".format(direction, finger_name))

        if not set(finger_name_list).issubset(data_set.org_model.bones) or not set(finger_name_list).issubset(data_set.rep_model.bones):
            logger.warning("손가락 본이 부족하기 때문에 손가락 위치 맞춤은 스킵 합니다.", decoration=MLogger.DECORATION_BOX)
            return []

        alignment_start_idx = len(self.target_links[data_set_idx].keys()) + 1

        for direction_idx, direction in enumerate(["左", "右"]):
            for finger_idx, finger_name in enumerate(["親指", "人指", "中指", "薬指", "小指"]):
                alignment_idx = (direction_idx * 5) + finger_idx + alignment_start_idx

                total_finger_name = "{0}{1}先実体".format(direction, finger_name)

                if total_finger_name not in data_set.org_model.bones or total_finger_name not in data_set.rep_model.bones:
                    # どっちかボーンがなければスルー
                    continue

                # 手のひらの長さ
                org_palm_length = (data_set.org_model.bones["{0}手首".format(direction)].position.distanceToPoint(data_set.org_model.bones[total_finger_name].position))
                rep_palm_length = (data_set.rep_model.bones["{0}手首".format(direction)].position.distanceToPoint(data_set.rep_model.bones[total_finger_name].position))

                # 指リンク
                org_finger_links = data_set.org_model.create_link_2_top_one(total_finger_name)
                rep_finger_links = data_set.rep_model.create_link_2_top_one(total_finger_name)

                # IK用リンク（エフェクタから追加していく）
                ik_links_list = []
                ik_count_list = []

                # if f"{direction}手捩" in data_set.rep_model.bones and f"{direction}手捩" in data_set.motion.bones:
                #     wrist_twist_bone = rep_finger_links.get("{0}手捩".format(direction))
                #     wrist_twist_bone.dot_near_limit = 0.97
                #     wrist_twist_bone.dot_far_limit = 0.8
                #     wrist_twist_bone.dot_single_limit = 0.9
                #     wrist_twist_bone.degree_limit = 57.2957

                elbow_bone = rep_finger_links.get("{0}ひじ".format(direction))
                elbow_bone.dot_near_limit = 0.97
                elbow_bone.dot_far_limit = 0.7
                elbow_bone.dot_single_limit = 0.9
                elbow_bone.degree_limit = 57.2957

                # if f"{direction}腕捩" in data_set.rep_model.bones and f"{direction}腕捩" in data_set.motion.bones:
                #     arm_twist_bone = rep_finger_links.get("{0}腕捩".format(direction))
                #     arm_twist_bone.dot_near_limit = 0.97
                #     arm_twist_bone.dot_far_limit = 0.8
                #     arm_twist_bone.dot_single_limit = 0.9
                #     arm_twist_bone.degree_limit = 57.2957

                arm_bone = rep_finger_links.get("{0}腕".format(direction))
                arm_bone.dot_near_limit = 0.97
                arm_bone.dot_far_limit = 0.8
                arm_bone.dot_single_limit = 0.9
                arm_bone.degree_limit = 57.2957

                ik_links = BoneLinks()
                ik_links.append(rep_finger_links.get(total_finger_name))

                # if f"{direction}手捩" in data_set.rep_model.bones and f"{direction}手捩" in data_set.motion.bones:
                #     ik_links.append(wrist_twist_bone)

                ik_links.append(elbow_bone)

                # if f"{direction}腕捩" in data_set.rep_model.bones and f"{direction}腕捩" in data_set.motion.bones:
                #     ik_links.append(arm_twist_bone)

                ik_links.append(arm_bone)
                ik_links_list.append(ik_links)
                ik_count_list.append(30)

                # # 끝부분リンクは不要
                # tip_ik_links = BoneLinks()
                # tip_ik_links.append(rep_finger_links.get(total_finger_name))
                # tip_ik_links.append(rep_finger_links.get("{0}手首".format(direction)))

                # 指リンク登録
                self.target_links[data_set_idx][alignment_idx] = \
                    ArmAlignmentOption(org_finger_links, rep_finger_links, ik_links_list, ik_count_list, None, \
                                       org_palm_length, rep_palm_length, data_set.org_model, data_set.rep_model, "{0}腕".format(direction), \
                                       total_finger_name, total_finger_name[:3], total_finger_name, self.options.arm_options.alignment_distance_finger, data_set.xz_ratio, 3)

            # 腕・ひじ・手首のキーフレ（なければスルー）
            bone_names.extend(["{0}腕".format(direction), "{0}腕捩".format(direction), "{0}ひじ".format(direction), "{0}手捩".format(direction), "{0}手首".format(direction)])

        return bone_names

    # 지정したモデル・方向の手のひら頂点
    def calc_wrist_entity_vertex(self, data_set_idx: int, model: PmxModel, target_model_type: str, direction: str):
        if "{0}手首実体".format(direction) not in model.bones:
            wrist_entity_vetex = model.get_wrist_vertex(direction)
            # XとZは手首の値（Yだけ頂点値）
            wrist_entity_pos = wrist_entity_vetex.position.copy()
            wrist_entity_pos.setX(model.bones["{0}手首".format(direction)].position.x())
            wrist_entity_pos.setZ(model.bones["{0}手首".format(direction)].position.z())
            wrist_entity_bone = Bone("{0}手首実体".format(direction), "", wrist_entity_pos, -1, 0, 0)
            wrist_entity_bone.index = len(model.bones.keys())
            model.bones[wrist_entity_bone.name] = wrist_entity_bone
            model.bone_indexes[wrist_entity_bone.index] = wrist_entity_bone.name
            model.wrist_entity_vertex[direction] = wrist_entity_vetex

        logger.info("【No.%s】%s모델의 %s손바닥 정점 INDEX: %s (%s)", (data_set_idx + 1), target_model_type, direction, \
                    model.wrist_entity_vertex[direction].index, model.wrist_entity_vertex[direction].position.to_log())

    # 処理対象データセットINDEX取得
    def get_target_set_idxs(self):
        target_data_set_idxs = []
        for data_set_idx, data_set in enumerate(self.options.data_set_list):
            if data_set.motion.motion_cnt <= 0:
                # モーションデータが無い場合、処理スキップ
                continue

            if (self.options.arm_options.arm_check_skip_flg or (data_set.rep_model.can_arm_sizing and data_set.org_model.can_arm_sizing)) \
                    and data_set_idx not in target_data_set_idxs:
                # ボーンセットがあり、腕系サイジング可能で、かつまだ登録されていない場合
                if "右手首" in data_set.org_model.bones and "左手首" in data_set.org_model.bones and "右手首" in data_set.rep_model.bones and "左手首" in data_set.rep_model.bones:
                    target_data_set_idxs.append(data_set_idx)
                else:
                    logger.info("【No.%s】원본 모델이나 변환용 모델에 '손목' 본이 부족하여 처리 대상에서 제외합니다.", (data_set_idx + 1))

        return target_data_set_idxs
