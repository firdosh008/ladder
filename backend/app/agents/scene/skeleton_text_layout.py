"""Reposition long ``text`` elements that sit atop rectangle ``label`` captions.

Excalidraw centers bound labels in shapes; models often add a separate body
``text`` block at the same center → overlap. This pass stacks body below a title
strip inside the same rectangle geometry."""

from __future__ import annotations

from app.models.db import SceneLayout, SceneSkeleton, SceneSkeletonElement

_TITLE_BAND_MIN = 36.0
_TITLE_BAND_MAX = 56.0
_TITLE_BAND_FRAC = 0.22
_PAD_X = 12.0
_PAD_BOTTOM = 10.0
_BODY_MIN_CHARS = 48


def _pt_in_rect(px: float, py: float, r: SceneSkeletonElement) -> bool:
    return r.x <= px <= r.x + r.width and r.y <= py <= r.y + r.height


def repack_rect_body_text_below_labels(scene: SceneSkeleton, layout: SceneLayout) -> SceneSkeleton:
    labeled_rects = [
        e
        for e in scene.elements
        if e.type == "rectangle"
        and e.label
        and (e.label.text or "").strip()
        and e.width > 0
        and e.height > 0
    ]
    if not labeled_rects:
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
        if len(raw) < _BODY_MIN_CHARS:
            new_els.append(el)
            continue
        # Canvas chrome
        if el.id in {"title-core", "note-aha"} or (el.y is not None and float(el.y) < 64):
            new_els.append(el)
            continue

        tcx = el.x + el.width / 2.0
        tcy = el.y + el.height / 2.0
        if not in_any_frame(tcx, tcy):
            new_els.append(el)
            continue

        host: SceneSkeletonElement | None = None
        for r in labeled_rects:
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

        band = min(
            _TITLE_BAND_MAX,
            max(_TITLE_BAND_MIN, host.height * _TITLE_BAND_FRAC),
        )
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
