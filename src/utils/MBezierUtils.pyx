# -*- coding: utf-8 -*-
#
from module.MMath import MRect, MVector2D, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from utils.MLogger import MLogger # noqa
import numpy as np
cimport numpy as np

import ctypes
ctypes.cdll.LoadLibrary(r".\bezier-2a44d276.dll")

import bezier
cimport bezier._curve

logger = MLogger(__name__, level=1)

# MMDでの補間曲線の最大値
INTERPOLATION_MMD_MAX = 127
# MMDの線形補間
LINEAR_MMD_INTERPOLATION = [MVector2D(0, 0), MVector2D(20, 20), MVector2D(107, 107), MVector2D(127, 127)]

# 回転補間曲線のインデックス
R_x1_idxs = [3, 18, 33, 48]
R_y1_idxs = [7, 22, 37, 52]
R_x2_idxs = [11, 26, 41, 56]
R_y2_idxs = [15, 30, 45, 60]

# X移動補間曲線のインデックス
MX_x1_idxs = [0, 0, 0, 0]
MX_y1_idxs = [19, 34, 49, 4]
MX_x2_idxs = [23, 38, 53, 8]
MX_y2_idxs = [27, 42, 57, 12]

# Y移動補間曲線のインデックス
MY_x1_idxs = [1, 16, 16, 16]
MY_y1_idxs = [5, 35, 50, 20]
MY_x2_idxs = [9, 39, 54, 24]
MY_y2_idxs = [13, 43, 58, 28]

# Z移動補間曲線のインデックス
MZ_x1_idxs = [2, 17, 32, 32]
MZ_y1_idxs = [6, 21, 51, 36]
MZ_x2_idxs = [10, 25, 55, 40]
MZ_y2_idxs = [14, 29, 59, 44]

BZ_TYPE_MX = "MX"
BZ_TYPE_MY = "MY"
BZ_TYPE_MZ = "MZ"
BZ_TYPE_R = "R"

def from_bz_type(bz_type: str):
    if bz_type == BZ_TYPE_MX:
        return MX_x1_idxs, MX_y1_idxs, MX_x2_idxs, MX_y2_idxs
    elif bz_type == BZ_TYPE_MY:
        return MY_x1_idxs, MY_y1_idxs, MY_x2_idxs, MY_y2_idxs
    elif bz_type == BZ_TYPE_MZ:
        return MZ_x1_idxs, MZ_y1_idxs, MZ_x2_idxs, MZ_y2_idxs
    else:
        return R_x1_idxs, R_y1_idxs, R_x2_idxs, R_y2_idxs


# https://github.com/vmichals/python-algos/blob/master/catmull_rom_spline.py
cdef double calc_catmull_rom_one_point(double x, double v0, double v1, double v2, double v3) except? -1:
    """Computes interpolated y-coord for given x-coord using Catmull-Rom.
    Computes an interpolated y-coordinate for the given x-coordinate between
    the support points v1 and v2. The neighboring support points v0 and v3 are
    used by Catmull-Rom to ensure a smooth transition between the spline
    segments.
    Args:
        x: the x-coord, for which the y-coord is needed
        v0: 1st support point
        v1: 2nd support point
        v2: 3rd support point
        v3: 4th support point
    """
    cdef double c1 = 1. * v1
    cdef double c2 = -.5 * v0 + .5 * v2
    cdef double c3 = 1. * v0 + -2.5 * v1 + 2. * v2 - 0.5 * v3
    cdef double c4 = -.5 * v0 + 1.5 * v1 + -1.5 * v2 + 0.5 * v3
    return (((c4 * x + c3) * x + c2) * x + c1)


# 指定したすべての値をカトマル曲線として計算する
cpdef np.ndarray calc_value_from_catmullrom(str bone_name, list fnos, list values):
    cdef np.ndarray[np.float_t, ndim=1] y_intpol
    cdef list prev_list, next_list
    cdef int fidx, sfno, efno, res
    cdef double t

    try:
        # create arrays for spline points
        y_intpol = np.empty(fnos[-1])

        # set the last x- and y-coord, the others will be set in the loop
        y_intpol[-1] = values[-1]

        prev_list = fnos[:-1]
        next_list = fnos[1:]

        # loop over segments (we have n-1 segments for n points)
        for fidx, (sfno, efno) in enumerate(zip(prev_list, next_list)):
            # loop over segments (we have n-1 segments for n points)
            res = efno - sfno

            if fidx == 0:
                # need to estimate an additional support point before the first
                y_intpol[sfno:efno] = np.array([
                    calc_catmull_rom_one_point(
                        t,
                        values[0] - (values[1] - values[0]),    # estimated start point,
                        values[0],
                        values[1],
                        values[2])
                    for t in np.linspace(0, 1, res, endpoint=False)])
            elif fidx == len(fnos) - 2:
                # need to estimate an additional support point after the last
                y_intpol[sfno:efno] = np.array([
                    calc_catmull_rom_one_point(
                        t,
                        values[fidx - 1],
                        values[fidx],
                        values[fidx + 1],
                        values[fidx + 1] + (values[fidx + 1] - values[fidx])    # estimated end point
                    ) for t in np.linspace(0, 1, res, endpoint=False)])
            else:
                y_intpol[sfno:efno] = np.array([
                    calc_catmull_rom_one_point(
                        t,
                        values[fidx - 1],
                        values[fidx],
                        values[fidx + 1],
                        values[fidx + 2]) for t in np.linspace(0, 1, res, endpoint=False)])

        return y_intpol
    except Exception as e:
        # エラーレベルは落として表に出さない
        logger.debug("카토마루 곡선값 생성 실패", e)
        return np.empty(1)


# 指定したすべての値を通るカトマル曲線からベジェ曲線を計算し、MMD補間曲線範囲内に収められた場合、そのベジェ曲線を返す
def join_value_2_bezier(fno: int, bone_name: str, values: list, offset=0, diff_limit=0.01):
    return_tuple = c_join_value_2_bezier(fno, bone_name, values, offset, diff_limit)
    return return_tuple[0], return_tuple[1]

cdef tuple c_join_value_2_bezier(int fno, str bone_name, list values, double offset, double diff_limit):
    if len(values) <= 2:
        # 次数が1の場合、線形補間
        logger.debug("차수 1: values: %s", values)
        return (LINEAR_MMD_INTERPOLATION, [])

    cdef np.ndarray[np.double_t, ndim=1] xs, yx
    cdef np.ndarray[np.float_t, ndim=1] bz_x, bz_y, reduce_bz_x, reduce_bz_y, bezier_x, diff_ys, full_ys, reduced_ys, diff_large
    cdef np.ndarray[np.float_t, ndim=2] nodes
    cdef list reduced_curve_list, joined_bz
    cdef tuple catmullrom_tuple
    cdef int degree

    try:
        # Xは次数（フレーム数）分移動
        xs = np.arange(0, len(values), dtype=np.float)
        # YはXの移動分を許容範囲とする
        ys = np.array(values, dtype=np.float)

        # カトマル曲線をベジェ曲線に変換する
        (bz_x, bz_y) = convert_catmullrom_2_bezier(np.concatenate([[None], xs, [None]]), np.concatenate([[None], ys, [None]]))
        logger.debug("bz_x: %s, bz_y: %s", bz_x, bz_y)

        if len(bz_x) == 0:
            # 始点と終点が指定されていて、カトマル曲線が描けなかった場合、線形補間
            logger.debug("캐트멀 곡선 실패: bz_x: %s", bz_x)
            return (LINEAR_MMD_INTERPOLATION, [])

        # 次数
        degree = int(len(bz_x) - 1)
        logger.test("degree: %s", degree)

        # すべての制御点を加味したベジェ曲線
        full_curve = bezier.Curve(np.asfortranarray([bz_x, bz_y]), degree=degree)

        if degree < 3:
            # 3次未満の場合、3次まで次数を増やす
            joined_curve = full_curve.elevate()
            for _ in range(1, 3 - degree):
                joined_curve = joined_curve.elevate()
        elif degree == 3:
            # 3次の場合、そのままベジェ曲線をMMD用に補間
            joined_curve = full_curve
        else:
            # 3次より多い場合、次数を減らす

            reduced_curve_list = []
            bz_x = full_curve.nodes[0]
            bz_y = full_curve.nodes[1]
            logger.test("START bz_x: %s, bz_y: %s", bz_x, bz_y)

            # 3次になるまでベジェ曲線を繋いで減らしていく
            while len(bz_x) > 4:
                reduced_curve_list = []

                for n in range(0, degree + 1, 5):
                    reduce_bz_x = bz_x[n:n + 5]
                    reduce_bz_y = bz_y[n:n + 5]
                    logger.test("n: %s, reduce_bz_x: %s, reduce_bz_y: %s", n, reduce_bz_x, reduce_bz_y)
                    reduced_curve = bezier.Curve(np.asfortranarray([reduce_bz_x, reduce_bz_y]), degree=(len(reduce_bz_x) - 1))

                    # 次数がある場合、減らす
                    if (len(reduce_bz_x) - 1) > 1:
                        reduced_curve = reduced_curve.reduce_()

                    logger.test("n: %s, nodes: %s", n, reduced_curve.nodes)

                    # リストに追加
                    reduced_curve_list.append(reduced_curve)

                bz_x = np.empty(0)
                bz_y = np.empty(0)

                for reduced_curve in reduced_curve_list:
                    bz_x = np.append(bz_x, reduced_curve.nodes[0])
                    bz_y = np.append(bz_y, reduced_curve.nodes[1])

                logger.test("NEXT bz_x: %s, bz_y: %s", bz_x, bz_y)

            logger.test("FINISH bz_x: %s, bz_y: %s", bz_x, bz_y)

            # bz_x = [full_curve.nodes[0][0]] + list(bz_x) + [full_curve.nodes[0][-1]]
            # bz_y = [full_curve.nodes[0][0]] + list(bz_y) + [full_curve.nodes[0][-1]]

            joined_curve = bezier.Curve(np.asfortranarray([bz_x, bz_y]), degree=(len(bz_x) - 1))

        logger.test("joined_curve: %s", joined_curve.nodes)

        # 全体のキーフレ
        bezier_x = np.arange(0, len(values), dtype=np.float)[1:]

        # 元の2つのベジェ曲線との交点を取得する
        full_ys = intersect_by_x(full_curve, bezier_x)
        logger.test("f: %s, %s, full_ys: %s", fno, bone_name, full_ys)

        # 次数を減らしたベジェ曲線との交点を取得する
        reduced_ys = intersect_by_x(joined_curve, bezier_x)
        logger.test("f: %s, %s, reduced_ys: %s", fno, bone_name, reduced_ys)

        # 交点の差を取得する(前後は必ず一致)
        diff_ys = np.concatenate([[0], np.array(full_ys) - np.array(reduced_ys)])

        # 差が大きい箇所をピックアップする
        diff_large = np.where(np.abs(diff_ys) > (diff_limit * (offset + 1)), 1, 0).astype(np.float)

        # 差が一定未満である場合、ベジェ曲線をMMD補間曲線に合わせる
        nodes = joined_curve.nodes

        # MMD用補間曲線に変換
        joined_bz = scale_bezier(MVector2D(nodes[0, 0], nodes[1, 0]), MVector2D(nodes[0, 1], nodes[1, 1]), \
                                 MVector2D(nodes[0, 2], nodes[1, 2]), MVector2D(nodes[0, 3], nodes[1, 3]))
        logger.debug("f: %s, %s, values: %s, nodes: %s, full_ys: %s, reduced_ys: %s, diff_ys: %s, diff_limit: %s, diff_large: %s, joined_bz: %s, %s, fit: %s", \
                     fno, bone_name, values, joined_curve.nodes, full_ys, reduced_ys, diff_ys, diff_limit, np.count_nonzero(diff_large) > 0, joined_bz[1], joined_bz[2], \
                     is_fit_bezier_mmd(joined_bz, offset))

        if np.count_nonzero(diff_large) > 0:
            # 差が大きい箇所がある場合、分割不可
            return (None, np.where(diff_large)[0].tolist())

        if not is_fit_bezier_mmd(joined_bz, offset):
            # 補間曲線がMMD補間曲線内に収まらない場合、NG

            # 差分の大きなところを返す
            diff_large = np.where(np.abs(diff_ys) > (diff_limit * 0.5 * (offset + 1)), 1, 0).astype(np.float)
            if np.count_nonzero(diff_large) > 0:
                return (None, np.where(diff_large)[0].tolist())

            # 差分の大きなところを返す
            diff_large = np.where(np.abs(diff_ys) > 0, 1, 0).astype(np.float)
            if np.count_nonzero(diff_large) > 0:
                return (None, np.where(diff_large)[0].tolist())

            return (None, [])

        # オフセット込みの場合、MMD用補間曲線枠内に収める
        fit_bezier_mmd(joined_bz)

        # すべてクリアした場合、補間曲線採用
        return (joined_bz, [])
    except Exception as e:
        # エラーレベルは落として表に出さない
        logger.debug("베지에 곡선 생성 실패", e)
        return (None, [])


cdef bint fit_bezier_mmd(list bzs):
    for bz in bzs:
        bz.effective()
        bz.setX(0 if bz.x() < 0 else INTERPOLATION_MMD_MAX if bz.x() > INTERPOLATION_MMD_MAX else bz.x())
        bz.setY(0 if bz.y() < 0 else INTERPOLATION_MMD_MAX if bz.y() > INTERPOLATION_MMD_MAX else bz.y())

    return True


# Catmull-Rom曲線の制御点(通過点)をBezier曲線の制御点に変換する
# http://defghi1977-onblog.blogspot.com/2014/09/catmull-rombezier.html
cdef tuple convert_catmullrom_2_bezier(np.ndarray xs, np.ndarray ys):

    cdef list bz_x = []
    cdef list bz_y = []
    cdef MVector2D p0, p1, p2, p3, B, C

    for x0, x1, x2, x3, y0, y1, y2, y3 in zip(xs[:-3], xs[1:-2], xs[2:-1], xs[3:], ys[:-3], ys[1:-2], ys[2:-1], ys[3:]):
        p0 = None if not x0 and not y0 else MVector2D(x0, y0)
        p1 = MVector2D(x1, y1)
        p2 = MVector2D(x2, y2)
        p3 = None if not x3 and not y3 else MVector2D(x3, y3)
        B = None
        C = None

        if not p0 and not p3:
            # 両方ない場合、無視
            continue

        if not p0 and p3:
            bz_x.append(p1.x())
            bz_y.append(p1.y())

            # p0が空の場合、始点
            B = (p1 * (1 / 2)) - p2 + (p3 * (1 / 2))
            C = (p1 * (-3 / 2)) + (p2 * 2) - (p3 * (1 / 2))

        if p0 and not p3:
            # p3が空の場合、終点
            B = (p0 * (1 / 2)) - p1 + (p2 * (1 / 2))
            C = (p0 * (-1 / 2)) + (p2 * (1 / 2))

        if p0 and p3:
            # それ以外は通過点
            B = p0 - (p1 * (5 / 2)) + (p2 * (4 / 2)) - (p3 * (1 / 2))
            C = (p0 * (-1 / 2)) + (p2 * (1 / 2))

        if not B or not C:
            logger.warning("p0: %s, p1: %s, p2: %s, p3: %s", p0, p1, p2, p3)

        # ベジェ曲線の制御点
        s1 = (C + (p1 * 3)) / 3
        s2 = (B - (p1 * 3) + (s1 * 6)) / 3

        bz_x.append(s1.x())
        bz_x.append(s2.x())

        bz_y.append(s1.y())
        bz_y.append(s2.y())

    bz_x.append(xs[-2])
    bz_y.append(ys[-2])

    return (np.array(bz_x, dtype=np.float64), np.array(bz_y, dtype=np.float64))


# 指定された複数のXと交わるそれぞれのYを返す
cdef np.ndarray intersect_by_x(curve, np.ndarray xs):
    cdef double x
    cdef list ys = []
    cdef np.ndarray[np.float_t, ndim=1] s_vals
    cdef np.ndarray[np.float_t, ndim=2] intersections

    for x in xs:
        # 交点を求める為のX線上の直線
        line1 = bezier.Curve(np.asfortranarray([[x, x], [-99999, 99999]]), degree=1)

        # 交点を求める（高精度は求めない）
        intersections = curve.intersect(line1, _verify=False)

        # tからyを求め直す
        s_vals = np.asfortranarray(intersections[0, :])

        # 評価する
        es = curve.evaluate_multi(s_vals)

        # 値が取れている場合、その値を設定する
        if es.shape == (2, 1):
            ys.append(es[1][0])
        # 取れていない場合、無視
        else:
            ys.append(0)

    return np.array(ys, dtype=np.float)


# 補間曲線を求める
# http://d.hatena.ne.jp/edvakf/20111016/1318716097
# https://pomax.github.io/bezierinfo
# https://shspage.hatenadiary.org/entry/20140625/1403702735
# https://bezier.readthedocs.io/en/stable/python/reference/bezier.curve.html#bezier.curve.Curve.evaluate
def evaluate(x1v: int, y1v: int, x2v: int, y2v: int, start: int, now: int, end: int):
    return_tuple = c_evaluate(x1v, y1v, x2v, y2v, start, now, end)
    return return_tuple[0], return_tuple[1], return_tuple[2]

cdef tuple c_evaluate(int x1v, int y1v, int x2v, int y2v, int start, int now, int end):
    if (now - start) == 0 or (end - start) == 0:
        return (0, 0, 0)

    cdef double x, x1, x2, y1, y2, t, s, ft, y
    cdef int i

    x = (now - start) / (end - start)
    x1 = x1v / INTERPOLATION_MMD_MAX
    x2 = x2v / INTERPOLATION_MMD_MAX
    y1 = y1v / INTERPOLATION_MMD_MAX
    y2 = y2v / INTERPOLATION_MMD_MAX

    t = 0.5
    s = 0.5

    # 二分法
    # logger.test("x1: %s, x2: %s, y1: %s, y2: %s, x: %s", x1, x2, y1, y2, x)
    for i in range(15):
        ft = (3 * (s * s) * t * x1) + (3 * s * (t * t) * x2) + (t * t * t) - x
        # logger.test("i: %s, 4 << i: %s, ft: %s(%s), t: %s, s: %s", i, (4 << i), ft, abs(ft) < 0.00001, t, s)

        if ft > 0:
            t -= 1 / (4 << i)
        else:
            t += 1 / (4 << i)

        s = 1 - t

    y = (3 * (s * s) * t * y1) + (3 * s * (t * t) * y2) + (t * t * t)

    # logger.test("y: %s, t: %s, s: %s", y, t, s)

    return (x, y, t)


# 指定されたtになるフレーム番号を取得する
def evaluate_by_t(x1v: int, y1v: int, x2v: int, y2v: int, start: int, end: int, t: float):
    return_tuple = c_evaluate_by_t(x1v, y1v, x2v, y2v, start, end, t)
    return return_tuple[0], return_tuple[1], return_tuple[2]

cdef tuple c_evaluate_by_t(int x1v, int y1v, int x2v, int y2v, int start, int end, double t):
    if (end - start) <= 1:
        # 差が1以内の場合、終了
        return (start, 0, t)

    cdef double x1, x2, y1, y2
    cdef int fno

    x1 = x1v / INTERPOLATION_MMD_MAX
    x2 = x2v / INTERPOLATION_MMD_MAX
    y1 = y1v / INTERPOLATION_MMD_MAX
    y2 = y2v / INTERPOLATION_MMD_MAX

    # 補間曲線
    curve1 = bezier.Curve(np.asfortranarray([[0, x1, x2, 1], [0, y1, y2, 1]]), degree=3)

    # 単一の評価(x, y)
    es = curve1.evaluate(t)

    # xに相当するフレーム番号
    fno = int(round_integer(start + ((end - start) * es[0, 0])))

    return (fno, es[1, 0], t)


# 3次ベジェ曲線の分割
def split_bezier_mmd(x1v: int, y1v: int, x2v: int, y2v: int, start: int, now: int, end: int):
    if (now - start) == 0 or (end - start) == 0:
        return 0, 0, 0, False, False, LINEAR_MMD_INTERPOLATION, LINEAR_MMD_INTERPOLATION

    # 3次ベジェ曲線を分割する
    return_tuple = split_bezier(x1v, y1v, x2v, y2v, start, now, end)
    x = return_tuple[0]
    y = return_tuple[1]
    t = return_tuple[2]
    before_bz = return_tuple[3]
    after_bz = return_tuple[4]

    # ベジェ曲線の値がMMD用に合っているかを加味して返す
    return x, y, t, is_fit_bezier_mmd(before_bz), is_fit_bezier_mmd(after_bz), before_bz, after_bz


# ベジェ曲線の値がMMD用に合っているか
def is_fit_bezier_mmd(bz: list, offset=0):
    for b in bz:
        if not (0 - offset <= b.x() <= INTERPOLATION_MMD_MAX + offset) or not (0 - offset <= b.y() <= INTERPOLATION_MMD_MAX + offset):
            # MMD用の範囲内でなければNG
            return False

    if bz[1].x() == bz[1].y() == bz[2].x() == bz[2].y() == 0:
        # 全部0なら不整合
        return False

    return True


# 3次ベジェ曲線の分割
# http://geom.web.fc2.com/geometry/bezier/cut-cb.html
cdef tuple split_bezier(int x1v, int y1v, int x2v, int y2v, int start, int now, int end):
    # 補間曲線の進んだ時間分を求める
    return_tuple = c_evaluate(x1v, y1v, x2v, y2v, start, now, end)
    cdef double x = return_tuple[0]
    cdef double y = return_tuple[1]
    cdef double t = return_tuple[2]

    cdef MVector2D A = MVector2D(0.0, 0.0)
    cdef MVector2D B = MVector2D(x1v / INTERPOLATION_MMD_MAX, y1v / INTERPOLATION_MMD_MAX)
    cdef MVector2D C = MVector2D(x2v / INTERPOLATION_MMD_MAX, y2v / INTERPOLATION_MMD_MAX)
    cdef MVector2D D = MVector2D(1.0, 1.0)

    cdef MVector2D E = A * (1 - t) + B * t
    cdef MVector2D F = B * (1 - t) + C * t
    cdef MVector2D G = C * (1 - t) + D * t
    cdef MVector2D H = E * (1 - t) + F * t
    cdef MVector2D I = F * (1 - t) + G * t # noqa
    cdef MVector2D J = H * (1 - t) + I * t

    # 新たな4つのベジェ曲線の制御点は、A側がAEHJ、C側がJIGDとなる。

    # スケーリング
    cdef list beforeBz = scale_bezier(A, E, H, J)
    cdef list afterBz = scale_bezier(J, I, G, D)

    return (x, y, t, beforeBz, afterBz)


# 分割したベジェのスケーリング
cdef list scale_bezier(MVector2D p1, MVector2D p2, MVector2D p3, MVector2D p4):
    cdef MVector2D diff = p4 - p1

    # nan対策
    cdef MVector2D s1 = scale_bezier_point(p1, p1, diff)
    cdef MVector2D s2 = scale_bezier_point(p2, p1, diff)
    cdef MVector2D s3 = scale_bezier_point(p3, p1, diff)
    cdef MVector2D s4 = scale_bezier_point(p4, p1, diff)

    cdef MVector2D bs1 = round_bezier_mmd(s1)
    cdef MVector2D bs2 = round_bezier_mmd(s2)
    cdef MVector2D bs3 = round_bezier_mmd(s3)
    cdef MVector2D bs4 = round_bezier_mmd(s4)

    return [bs1, bs2, bs3, bs4]


# nan対策を加味したベジェ曲線の点算出
cdef MVector2D scale_bezier_point(MVector2D pn, MVector2D p1, MVector2D diff):
    cdef MVector2D s = (pn - p1) / diff

    # logger.test("diff: %s", diff)
    # logger.test("(pn-p1): %s", (pn-p1))
    # logger.test("s: %s", s)

    # nanになったら0決め打ち
    s.effective()

    return s


# ベジェ曲線をMMD用の数値に丸める
cdef MVector2D round_bezier_mmd(MVector2D target):
    cdef MVector2D t2 = MVector2D()

    # XとYをそれぞれ整数(0-127)に丸める
    t2.setX(round_integer(target.x() * INTERPOLATION_MMD_MAX))
    t2.setY(round_integer(target.y() * INTERPOLATION_MMD_MAX))

    return t2


cdef int round_integer(double t):
    # 一旦整数部にまで持ち上げる
    cdef double t2 = t * 1000000

    # pythonは偶数丸めなので、整数部で丸めた後、元に戻す
    return round(round(t2, -6) / 1000000)
