# -*- coding: utf-8 -*-
#
import csv
import logging
import os
import traceback
from datetime import datetime

from mmd.PmxData import PmxModel # noqa
from mmd.VmdData import VmdMotion, VmdBoneFrame, VmdCameraFrame, VmdInfoIk, VmdLightFrame, VmdMorphFrame, VmdShadowFrame, VmdShowIkFrame # noqa
from mmd.VmdWriter import VmdWriter
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from module.MOptions import MVmdOptions, MOptionsDataSet
from utils import MFileUtils
from utils.MException import SizingException
from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)


class ConvertVmdService():
    def __init__(self, options: MVmdOptions):
        self.options = options

    def execute(self):
        logging.basicConfig(level=self.options.logging_level, format="%(message)s [%(module_name)s]")

        try:
            service_data_txt = "VMD변환 처리 실행\n------------------------\nexe버전: {version_name}\n".format(version_name=self.options.version_name) \

            service_data_txt = "{service_data_txt}　　본CSV: {bone_csv}\n".format(service_data_txt=service_data_txt,
                                    bone_csv=os.path.basename(self.options.bone_csv_path)) # noqa
            service_data_txt = "{service_data_txt}　　모프CSV: {morph_csv}\n".format(service_data_txt=service_data_txt,
                                    morph_csv=os.path.basename(self.options.morph_csv_path)) # noqa
            service_data_txt = "{service_data_txt}　　카메라CSV: {camera_csv}\n".format(service_data_txt=service_data_txt,
                                    camera_csv=os.path.basename(self.options.camera_csv_path)) # noqa

            logger.info(service_data_txt, decoration=MLogger.DECORATION_BOX)

            # 処理に成功しているか
            result = self.convert_vmd()

            return result
        except SizingException as se:
            logger.error("VMD 변환 처리기 처리할 수 없는 데이터로 종료되었습니다.\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
        except Exception:
            logger.critical("VMD 변환 처리가 의도치 않은 오류로 종료되었습니다.\n\n%s", traceback.format_exc(), decoration=MLogger.DECORATION_BOX)
        finally:
            logging.shutdown()

    # VMD変換処理実行
    def convert_vmd(self):
        dt_now = datetime.now()

        bone_fpath = None
        bone_motion = VmdMotion()

        if self.options.bone_csv_path and os.path.exists(self.options.bone_csv_path):
            # ボーンモーションCSVディレクトリパス
            motion_csv_dir_path = MFileUtils.get_dir_path(self.options.bone_csv_path)
            # ボーンモーションCSVファイル名・拡張子
            motion_csv_file_name, _ = os.path.splitext(os.path.basename(self.options.bone_csv_path))

            bone_fpath = "{0}\\{1}_bone_{2:%Y%m%d_%H%M%S}.vmd".format(motion_csv_dir_path, motion_csv_file_name, dt_now)

            # ボーンCSV読み込み
            with open(self.options.bone_csv_path, encoding='cp932', mode='r') as f:
                reader = csv.reader(f)
                next(reader)  # ヘッダーを読み飛ばす

                cnt = 0
                for ridx, row in enumerate(reader):
                    bf = VmdBoneFrame()
                    rno = ridx + 1

                    try:
                        if len(row) < 0 or not row[0]:
                            logger.error("[본]%s행 째 본 이름(1열째)이 설정되어 있지 않습니다", rno, decoration=MLogger.DECORATION_BOX)
                            return False

                        # ボーン名
                        bf.set_name(row[0])
                    except Exception as e:
                        logger.error("[본] %s행 본 이름 읽기에 실패했습니다\n%s", rno, e, decoration=MLogger.DECORATION_BOX)
                        return False

                    try:
                        if len(row) < 1 or not row[1]:
                            logger.error("[본] %s행째 프레임 번호(2열째)가 설정되어 있지 않습니다.", rno, decoration=MLogger.DECORATION_BOX)
                            return False

                        # 프레임
                        bf.fno = int(float(row[1]))

                        if bf.fno < 0:
                            logger.error("[본] %s행째 프레임 번호(2열째)에 음수로 설정되어 있습니다.", rno, decoration=MLogger.DECORATION_BOX)
                            return False

                    except Exception as e:
                        logger.error("[본] %s행째 프레임 번호 판독에 실패했습니다\n프레임 번호는 반각 숫자만 입력 가능합니다.\n%s", rno, e, decoration=MLogger.DECORATION_BOX)
                        return False

                    try:
                        if len(row) < 4 or not row[2] or not row[3] or not row[4]:
                            logger.error("[본] %s행째 위치(3-5번째 열) 중 하나가 설정되어 있지 않습니다.", rno, decoration=MLogger.DECORATION_BOX)
                            return False

                        # 위치
                        bf.position = MVector3D(float(row[2]), float(row[3]), float(row[4]))
                    except Exception as e:
                        logger.error("[본] %s행째 위치 판독에 실패했습니다\n위치는 반각숫자, 부호, 소수점만 입력 가능합니다.\n%s", rno, e, decoration=MLogger.DECORATION_BOX)
                        return False

                    try:
                        if len(row) < 7 or not row[5] or not row[6] or not row[7]:
                            logger.error("[본] %s행째 회전(6-8번째 열)중 하나가 설정되어 있지 않습니다", rno, decoration=MLogger.DECORATION_BOX)
                            return False

                        # 회전
                        bf.rotation = MQuaternion.fromEulerAngles(float(row[5]), float(row[6]) * -1, float(row[7]) * -1)
                    except Exception as e:
                        logger.error("[본] %s행 회전의 판독에 실패했습니다\n위치는 반각숫자, 부호, 소수점만 입력 가능합니다.\n%s", rno, e, decoration=MLogger.DECORATION_BOX)
                        return False

                    try:
                        if len(row) < 71:
                            logger.error("[본] %s행째의 보간 곡선(9-72열째) 중 하나가 설정되어 있지 않습니다.", rno, decoration=MLogger.DECORATION_BOX)
                            return False

                        for cidx in range(8, 72):
                            if not row[cidx]:
                                logger.error("[본] %s행 보간곡선의 %s번째가 설정되어 있지 않습니다.", rno, cidx - 7, decoration=MLogger.DECORATION_BOX)
                                return False

                        # 보간곡선(一旦floatで読み込んで指数等も読み込んだ後、intに変換)
                        bf.interpolation = [int(float(row[8])), int(float(row[9])), int(float(row[10])), int(float(row[11])), int(float(row[12])), int(float(row[13])), \
                                            int(float(row[14])), int(float(row[15])), int(float(row[16])), int(float(row[17])), int(float(row[18])), int(float(row[19])), \
                                            int(float(row[20])), int(float(row[21])), int(float(row[22])), int(float(row[23])), int(float(row[24])), int(float(row[25])), \
                                            int(float(row[26])), int(float(row[27])), int(float(row[28])), int(float(row[29])), int(float(row[30])), int(float(row[31])), \
                                            int(float(row[32])), int(float(row[33])), int(float(row[34])), int(float(row[35])), int(float(row[36])), int(float(row[37])), \
                                            int(float(row[38])), int(float(row[39])), int(float(row[40])), int(float(row[41])), int(float(row[42])), int(float(row[43])), \
                                            int(float(row[44])), int(float(row[45])), int(float(row[46])), int(float(row[47])), int(float(row[48])), int(float(row[49])), \
                                            int(float(row[50])), int(float(row[51])), int(float(row[52])), int(float(row[53])), int(float(row[54])), int(float(row[55])), \
                                            int(float(row[56])), int(float(row[57])), int(float(row[58])), int(float(row[59])), int(float(row[60])), int(float(row[61])), \
                                            int(float(row[62])), int(float(row[63])), int(float(row[64])), int(float(row[65])), int(float(row[66])), int(float(row[67])), \
                                            int(float(row[68])), int(float(row[69])), int(float(row[70])), int(float(row[71]))]

                        for bidx, bi in enumerate(bf.interpolation):
                            if 0 > bi:
                                logger.error("[본] %s행째의 보간곡선(%s열째)에 음수로 설정되어 있습니다.", rno, bidx + 9, decoration=MLogger.DECORATION_BOX)
                                return False

                    except Exception as e:
                        logger.error("[본] %s행 보간곡선 읽기가 실패했습니다\n위치는 반각숫자만 입력 가능합니다.\n%s", rno, e, decoration=MLogger.DECORATION_BOX)
                        return False

                    bf.read = True
                    bf.key = True

                    if bf.name not in bone_motion.bones:
                        bone_motion.bones[bf.name] = {}

                    bone_motion.bones[bf.name][bf.fno] = bf

                    cnt += 1

                    if cnt % 10000 == 0:
                        logger.info("[본] %s키째 : 종료", cnt)

        if self.options.morph_csv_path and os.path.exists(self.options.morph_csv_path):
            # モーフモーションCSVディレクトリパス
            motion_csv_dir_path = MFileUtils.get_dir_path(self.options.morph_csv_path)
            # モーフモーションCSVファイル名・拡張子
            motion_csv_file_name, _ = os.path.splitext(os.path.basename(self.options.morph_csv_path))

            if not bone_fpath:
                bone_fpath = "{0}\\{1}_morph_{2:%Y%m%d_%H%M%S}.vmd".format(motion_csv_dir_path, motion_csv_file_name, dt_now)

            # モーフCSV読み込み
            with open(self.options.morph_csv_path, encoding='utf-8', mode='r') as f:
                reader = csv.reader(f)
                next(reader)  # ヘッダーを読み飛ばす

                cnt = 0
                for ridx, row in enumerate(reader):
                    mf = VmdMorphFrame()
                    rno = ridx + 1

                    try:
                        if len(row) < 0 or not row[0]:
                            logger.error("[모프] %s행째의 모프명(1열째)이 설정되어 있지 않습니다.", rno, decoration=MLogger.DECORATION_BOX)
                            return False

                        # ボーン名
                        mf.set_name(row[0])
                    except Exception as e:
                        logger.error("[모프] %s행 모프 이름 판독에 실패했습니다\n%s", rno, e, decoration=MLogger.DECORATION_BOX)
                        return False

                    try:
                        if len(row) < 1 or not row[1]:
                            logger.error("[모프] %s행째 프레임 번호(2열째)가 설정되어 있지 않습니다.", rno, decoration=MLogger.DECORATION_BOX)
                            return False

                        # 프레임
                        mf.fno = int(float(row[1]))

                        if mf.fno < 0:
                            logger.error("[모프] %s행째 프레임 번호(2열째)에 음수로 설정되어 있습니다.", rno, decoration=MLogger.DECORATION_BOX)
                            return False
                    except Exception as e:
                        logger.error("[모프] %s행째 프레임 번호 판독에 실패했습니다\n프레임 번호는 반각 숫자만 입력 가능합니다.\n%s", rno, e, decoration=MLogger.DECORATION_BOX)
                        return False

                    try:
                        if len(row) < 2 or not row[2]:
                            logger.error("[모프] %s행째의 크기(3열째)가 설정되어 있지 않습니다.", rno, decoration=MLogger.DECORATION_BOX)
                            return False

                        # 値
                        mf.ratio = float(row[2])
                    except Exception as e:
                        logger.error("[모프] %s줄 크기 판독에 실패했습니다\n 크기는 반각 숫자, 부호, 소수점만 입력 가능합니다.\n%s", rno, e, decoration=MLogger.DECORATION_BOX)
                        return False

                    if mf.name not in bone_motion.morphs:
                        bone_motion.morphs[mf.name] = {}

                    bone_motion.morphs[mf.name][mf.fno] = mf

                    cnt += 1

                    if cnt % 1000 == 0:
                        logger.info("[모프] %s키째 : 종료", cnt)

        if len(bone_motion.bones.keys()) > 0 or len(bone_motion.morphs.keys()) > 0:
            # ボーンかモーフのキーがある場合、まとめて出力

            model = PmxModel()
            model.name = "CSV Convert Model"
            data_set = MOptionsDataSet(bone_motion, model, model, bone_fpath, False, False, [], None, 0, [])

            VmdWriter(data_set).write()

            logger.info("본 모프 모션VMD: %s", bone_fpath, decoration=MLogger.DECORATION_BOX)

        if self.options.camera_csv_path and os.path.exists(self.options.camera_csv_path):
            # 카메라モーションCSVディレクトリパス
            motion_csv_dir_path = MFileUtils.get_dir_path(self.options.camera_csv_path)
            # 카메라モーションCSVファイル名・拡張子
            motion_csv_file_name, _ = os.path.splitext(os.path.basename(self.options.camera_csv_path))

            camera_fpath = "{0}\\{1}_camera_{2:%Y%m%d_%H%M%S}.vmd".format(motion_csv_dir_path, motion_csv_file_name, dt_now)
            camera_motion = VmdMotion()

            # 카메라CSV読み込み
            with open(self.options.camera_csv_path, encoding='cp932', mode='r') as f:
                reader = csv.reader(f)
                next(reader)  # ヘッダーを読み飛ばす

                cnt = 0
                for ridx, row in enumerate(reader):
                    cf = VmdCameraFrame()
                    rno = ridx + 1

                    try:
                        if len(row) < 1 or not row[0]:
                            logger.error("[카메라] %s행의 프레임 번호(1번째 열)가설정되어 있지 않습니다", rno, decoration=MLogger.DECORATION_BOX)
                            return False

                        # 프레임
                        cf.fno = int(row[0])

                        if cf.fno < 0:
                            logger.error("[카메라] %s행의 프레임 번호(1번째 열)に음수로 설정되어 있습니다.", rno, decoration=MLogger.DECORATION_BOX)
                            return False
                    except Exception as e:
                        logger.error("[카메라] %s행의 프레임 번호를 읽는데 실패했습니다\n프레임번호는  반각숫자만 입력 가능합니다.\n%s", rno, e, decoration=MLogger.DECORATION_BOX)
                        return False

                    try:
                        if len(row) < 3 or not row[1] or not row[2] or not row[3]:
                            logger.error("[카메라] %s행의위치(2-4번째 열)중 하나 가설정되어 있지 않습니다", rno, decoration=MLogger.DECORATION_BOX)
                            return False

                        # 위치
                        cf.position = MVector3D(float(row[1]), float(row[2]), float(row[3]))
                    except Exception as e:
                        logger.error("[카메라] %s행의 위치를 읽는데 실패했습니다\n위치는 반각숫자,부호,소수점만 입력 가능합니다.\n%s", rno, e, decoration=MLogger.DECORATION_BOX)
                        return False

                    try:
                        if len(row) < 6 or not row[4] or not row[5] or not row[6]:
                            logger.error("[카메라] %s행의 회전(5-7번째 열)중 하나가 설정되어 있지 않습니다", rno, decoration=MLogger.DECORATION_BOX)
                            return False

                        # 회전(オイラー角)
                        cf.euler = MVector3D(float(row[4]), float(row[5]), float(row[6]))
                    except Exception as e:
                        logger.error("[카메라] %s행의 회전을 읽는데 실패했습니다\n회전은 반각숫자,부호,소수점만입력가능합니다.\n%s", rno, e, decoration=MLogger.DECORATION_BOX)
                        return False

                    try:
                        if len(row) < 7 or not row[7]:
                            logger.error("[카메라] %s행의 거리(8번째 열)가 설정되어 있지 않습니다", rno, decoration=MLogger.DECORATION_BOX)
                            return False

                        # 거리
                        cf.length = -(float(row[7]))
                    except Exception as e:
                        logger.error("[카메라] %s행의거리를 읽는데 실패했습니다\n거리는 반각숫자,부호,소수점만입력가능합니다.\n%s", rno, e, decoration=MLogger.DECORATION_BOX)
                        return False

                    try:
                        if len(row) < 8 or not row[8]:
                            logger.error("[카메라] %s행의 시야각(9번째 열)이설정되어 있지 않습니다", rno, decoration=MLogger.DECORATION_BOX)
                            return False

                        # 시야각
                        cf.angle = int(row[8])

                        if cf.angle < 0:
                            logger.error("[카메라] %s행의 시야각(9번째 열)이 음수로 설정되어 있습니다.", rno, decoration=MLogger.DECORATION_BOX)
                            return False

                    except Exception as e:
                        logger.error("[카메라] %s행의시야각을 읽는데 실패했습니다\n시야각은 반각숫자만 입력 가능합니다.\n%s", rno, e, decoration=MLogger.DECORATION_BOX)
                        return False

                    try:
                        if len(row) < 8 or not row[9]:
                            logger.error("[카메라] %s행의Perspective(10번째 열)가 설정되어 있지 않습니다", rno, decoration=MLogger.DECORATION_BOX)
                            return False

                        # Perspective
                        cf.perspective = int(row[9])

                        if cf.perspective not in [0, 1]:
                            logger.error("[카메라] %s행의Perspective(10번째 열)에 0, 1 이외의 값이 설정되어 있습니다", rno, decoration=MLogger.DECORATION_BOX)
                            return False
                    except Exception as e:
                        logger.error("[카메라] %s행의Perspective를 읽는데 실패했습니다\nPerspective에는 0, 1만 입력 가능합니다.\n%s", rno, e, decoration=MLogger.DECORATION_BOX)
                        return False

                    try:
                        if len(row) < 33:
                            logger.error("[카메라] %s행의 보간곡선(11-34번째 열)중 하나가 설정되어 있지 않습니다", rno, decoration=MLogger.DECORATION_BOX)
                            return False

                        for cidx in range(10, 34):
                            if not row[cidx]:
                                logger.error("[카메라] %s행의 보간곡선의 %s번째가설정되어 있지 않습니다", rno, cidx - 9, decoration=MLogger.DECORATION_BOX)
                                return False

                        # 보간곡선(一旦floatで読み込んで指数等も読み込んだ後、intに変換)
                        cf.interpolation = [int(float(row[10])), int(float(row[11])), int(float(row[12])), int(float(row[13])), int(float(row[14])), int(float(row[15])), \
                                            int(float(row[16])), int(float(row[17])), int(float(row[18])), int(float(row[19])), int(float(row[20])), int(float(row[21])), \
                                            int(float(row[22])), int(float(row[23])), int(float(row[24])), int(float(row[25])), int(float(row[26])), int(float(row[27])), \
                                            int(float(row[28])), int(float(row[29])), int(float(row[30])), int(float(row[31])), int(float(row[32])), int(float(row[33]))]

                        for cidx, ci in enumerate(cf.interpolation):
                            if 0 > ci:
                                logger.error("[카메라] %s행의 보간곡선(%s번째 열)이 음수로 설정되어 있습니다.", rno, cidx + 11, decoration=MLogger.DECORATION_BOX)
                                return False

                    except Exception as e:
                        logger.error("[카메라] %s행의 보간곡선을 읽는데 실패했습니다\n위치는 반각숫자만 입력 가능합니다.\n%s", rno, e, decoration=MLogger.DECORATION_BOX)
                        return False

                    camera_motion.cameras[cf.fno] = cf

                    cnt += 1

                    if cnt % 500 == 0:
                        logger.info("[카메라] %s키째:완료", cnt)

            if len(camera_motion.cameras) > 0:
                # ボーンかモーフのキーがある場合、まとめて出力

                model = PmxModel()
                model.name = "카메라, 조명"
                data_set = MOptionsDataSet(camera_motion, model, model, camera_fpath, False, False, [], None, 0, [])

                VmdWriter(data_set).write()

                logger.info("카메라 모션 VMD: %s", camera_fpath, decoration=MLogger.DECORATION_BOX)

        return True



