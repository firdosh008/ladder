"""Reposition ``text`` elements that collide with bound shape captions.

Excalidraw centers bound labels in shapes; models often add a separate body
``text`` block at the same vertical band → overlap. This pass stacks body below a
title strip inside the host shape."""

from __future__ import annotations

from app.models.db import SceneLayout, SceneSkeleton, SceneSkeletonElement

_TITLE_BAND_MIN = 36.0
_TITLE_BAND_MAX = 56.0
_TITLE_BAND_FRAC = 0.22
_PAD_X = 12.0
_PAD_BOTTOM = 10.0
"""Minimum characters before we consider standalone body copy — lower caps catch short subtitles."""
_BODY_MIN_CHARS = 12
_BAND_EPS = 4.0

_LABEL_HOST_TYPES = frozenset({"rectangle", "diamond"})


def _pt_in_rect(px: float, py: float, r: SceneSkeletonElement) -> bool:
    return r.x <= px <= r.x + r.width and r.y <= py <= r.y + r.height


def _title_band_height(host: SceneSkeletonElement) -> float:
    return min(
        _TITLE_BAND_MAX,
        max(_TITLE_BAND_MIN, host.height * _TITLE_BAND_FRAC),
    )


def _text_overlaps_title_band(
    el: SceneSkeletonElement, host: SceneSkeletonElement, band: float
) -> bool:
    """True when the text bbox vertically intersects the top caption strip."""
    strip_bottom = host.y + band
    text_top = float(el.y)
    text_bottom = el.y + el.height
    return text_bottom > host.y + _BAND_EPS and text_top < strip_bottom - _BAND_EPS


def repack_rect_body_text_below_labels(scene: SceneSkeleton, layout: SceneLayout) -> SceneSkeleton:
    labeled_hosts = [
        e
        for e in scene.elements
        if e.type in _LABEL_HOST_TYPES
        and e.label
        and (e.label.text or "").strip()
        and e.width > 0
        and e.height > 0
    ]
    if not labeled_hosts:
        return scene

    frame_boxes = [(float(f.x), float(f.y), float(f.width), float(f.height)) for f in layout.frames]

    def in_any_frame(cx: float, cy: float) -> bool:
        for fx, fy, fw, fh in frame_boxes:
            if fx <= cx <= fx + fw and fy <= cy <= fy + fh:
                return True
        return not frame_boxes

    new_els: list[SceneSkeletonElement] = []
    for el in scene.elements:
        if el.type != "text" or not (el.text or "").strip():
            new_els.append(el)
            continue
        raw = (el.text or "").strip()

        # Canvas chrome / hero title row — leave placement untouched.
        if el.id in {"title-core", "note-aha"} or float(el.y) < 64:
            new_els.append(el)
            continue

        tcx = el.x + el.width / 2.0
        tcy = el.y + el.height / 2.0
        if not in_any_frame(tcx, tcy):
            new_els.append(el)
            continue

        host: SceneSkeletonElement | None = None
        for r in labeled_hosts:
            if _pt_in_rect(tcx, tcy, r):
                host = r
                break
        if host is None:
            new_els.append(el)
            continue

        cap = (host.label.text or "").strip() if host.label else ""
        # Identical to bound caption — leave placement to the host label.
        if cap and raw == cap:
            new_els.append(el)
            continue

        band = _title_band_height(host)
        overlaps = _text_overlaps_title_band(el, host, band)
        if len(raw) < _BODY_MIN_CHARS and not overlaps:
            new_els.append(el)
            continue

        ny = host.y + band
        nx = host.x + _PAD_X
        nw = max(44.0, host.width - 2 * _PAD_X)
        nh = max(48.0, host.y + host.height - ny - _PAD_BOTTOM)

        new_els.append(
            el.model_copy(
                update={
                    "x": nx,
                    "y": ny,
                    "width": nw,
                    "height": nh,
                }
            )
        )

    return SceneSkeleton(
        canvas_width=scene.canvas_width,
        canvas_height=scene.canvas_height,
        background_color=scene.background_color,
        elements=new_els,
        notes=scene.notes,
        files=scene.files,
    )
