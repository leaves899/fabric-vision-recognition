"""Operator-confirmed, two-point physical yarn-axis geometry.

This is an input adapter for frozen V4, not a yarn classifier. It does not
infer the physical yarn from texture, FFT, gradients or artificial lattice.
"""
from __future__ import annotations
import math
import numpy as np
import cv2


def normalize_v4_rotation(axis_deg: float) -> float:
    """Rotation passed to OpenCV getRotationMatrix2D to make image-space axis horizontal.

    Axis is undirected: 0 and 180 are identical. Returns [-90, 90).
    """
    return float((axis_deg + 90.0) % 180.0 - 90.0)


def reference_from_two_points(points, image_shape, *, corners=None,
                              homography=None, confirmed=False) -> dict:
    if points is None or not isinstance(points,(list,tuple)) or len(points)!=2:
        raise ValueError('请先在图片上选择同一根真实纱线的两个参考点')
    original=np.asarray(points,dtype=np.float64)
    if original.shape!=(2,2) or not np.isfinite(original).all():
        raise ValueError('纱线参考点必须为两个有限坐标 [x,y]')
    height,width=image_shape[:2]
    if np.any(original[:,0]<0) or np.any(original[:,0]>=width) or np.any(original[:,1]<0) or np.any(original[:,1]>=height):
        raise ValueError('纱线参考点超出原图范围')
    delta=original[1]-original[0]
    separation=float(np.linalg.norm(delta))
    if separation<20:
        raise ValueError('两个参考点距离过近（小于 20 px），无法可靠确定方向')
    if not confirmed:
        raise ValueError('需要勾选“已确认两点属于同一根真实纱线”后才能分析')
    before=float(math.degrees(math.atan2(delta[1],delta[0])) % 180.0)
    pts_in_roi=original.copy()
    if homography is not None:
        if corners is None:
            raise ValueError('透视变换缺少原图四角')
        poly=np.asarray(corners,dtype=np.float32)
        for p in original:
            if cv2.pointPolygonTest(poly,tuple(map(float,p)),False)<0:
                raise ValueError('纱线参考点必须位于 5cm 标定框的内侧区域')
        H=np.asarray(homography,dtype=np.float64)
        if H.shape!=(3,3) or not np.isfinite(H).all():
            raise ValueError('无效的标定单应矩阵')
        pts_in_roi=cv2.perspectiveTransform(original.astype(np.float32).reshape(1,2,2),H)[0].astype(np.float64)
    roi_delta=pts_in_roi[1]-pts_in_roi[0]
    if np.linalg.norm(roi_delta)<15:
        raise ValueError('透视校正后参考点距离过近，请重新选择距离更远的可见纱段')
    roi_angle=float(math.degrees(math.atan2(roi_delta[1],roi_delta[0])) % 180.0)
    v4_rotation=normalize_v4_rotation(roi_angle)
    return {
        'source':'USER_TWO_POINT_SAME_REAL_YARN',
        'confirmed_by_operator': True,
        'image_points_px': original.tolist(),
        'roi_points_px':pts_in_roi.tolist(),
        'point_distance_image_px':round(separation,2),
        'reference_axis_image_deg':round(before,4),
        'reference_axis_roi_deg':round(roi_angle,4),
        'v4_adapter_rotation_deg':round(v4_rotation,4),
        'reference_group_meaning':'按这条参考纱线的轴向对齐 V4 第一组(水平候选组 A)，不自动判定经纬身份',
        'automatic_rotation_estimation':False,
        'warning':'人工选取并确认的方向，只能保证 V4 使用这个几何参考角度；不证明 V4 候选线均为真实单根纱线',
    }
