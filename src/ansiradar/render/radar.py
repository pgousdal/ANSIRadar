"""Pure radar frame renderer."""

from dataclasses import dataclass

from ansiradar import __version__
from ansiradar.models import PositionedAircraft
from ansiradar.radar.projection import project_polar, range_nm_from_km
from ansiradar.render.buffer import Cell, ScreenBuffer
from ansiradar.render.layout import RadarLayout, calculate_layout
from ansiradar.render.symbols import symbols


@dataclass(frozen=True, slots=True)
class RadarRenderOptions:
    range_nm: float = 100.0
    charset: str = "ascii"
    color: bool = False
    label: str = "callsign"
    units: str = "aviation"
    ground: bool = True
    selected_icao: str | None = None
    status: str = ""


def _cell(
    char: str,
    *,
    bold: bool = False,
    inverse: bool = False,
    foreground: int | None = None,
) -> Cell:
    return Cell(char, foreground=foreground, bold=bold, inverse=inverse)


def _draw_ring(
    buffer: ScreenBuffer, layout: RadarLayout, radius: float, char: str
) -> None:
    for bearing in range(0, 360, 5):
        point = project_polar(
            bearing,
            radius,
            layout.radar_width,
            layout.center_x,
            layout.center_y,
            layout.radar_width / 2 - 2,
            layout.radar_height / 2 - 1,
        )
        # Radius is represented by the caller as a fraction of max range.
        if (
            0 <= point.x < buffer.width
            and layout.radar_y <= point.y < layout.radar_y + layout.radar_height
        ):
            buffer.set_cell(point.x, point.y, char)


def _label_for(item: PositionedAircraft, mode: str) -> str:
    if mode == "none":
        return ""
    if mode == "icao":
        return item.aircraft.icao
    return item.aircraft.callsign or item.aircraft.icao


def render_radar(
    positioned: tuple[PositionedAircraft, ...],
    *,
    width: int = 80,
    height: int = 24,
    options: RadarRenderOptions | None = None,
) -> ScreenBuffer:
    options = options or RadarRenderOptions()
    buffer = ScreenBuffer(width, height)
    layout = calculate_layout(width, height)
    charset = options.charset
    syms = symbols(charset)
    if width == 0 or height == 0:
        return buffer
    border = "ascii" if charset == "ascii" else charset
    buffer.box(0, 0, width, height, border)
    title = f" ANSIRadar {__version__} "
    buffer.clipped_text(max(1, (width - len(title)) // 2), 0, title, max(0, width - 2))
    if layout.too_small:
        buffer.clipped_text(
            2, height // 2, "Terminal too small (minimum 60x20)", max(0, width - 4)
        )
        return buffer
    buffer.clipped_text(layout.center_x, layout.radar_y, "N", 1)
    buffer.clipped_text(max(0, layout.radar_x), layout.center_y, "W", 1)
    buffer.clipped_text(
        min(width - 1, layout.radar_x + layout.radar_width - 1), layout.center_y, "E", 1
    )
    buffer.clipped_text(
        layout.center_x, layout.radar_y + layout.radar_height - 1, "S", 1
    )
    # Rings are sampled ellipses, keeping the center and cardinal orientation stable.
    for fraction in (0.25, 0.5, 0.75, 1.0):
        rx = (layout.radar_width / 2 - 2) * fraction
        ry = (layout.radar_height / 2 - 1) * fraction
        for bearing in range(0, 360, 5):
            point = project_polar(
                bearing,
                fraction * options.range_nm,
                options.range_nm,
                layout.center_x,
                layout.center_y,
                rx,
                ry,
            )
            if (
                layout.radar_x <= point.x < layout.radar_x + layout.radar_width
                and layout.radar_y <= point.y < layout.radar_y + layout.radar_height
            ):
                if buffer.get_cell(point.x, point.y).char == " ":
                    buffer.set_cell(point.x, point.y, syms["ring"])
    buffer.set_cell(
        layout.center_x,
        layout.center_y,
        _cell(syms["receiver"], bold=True, foreground=2),
    )
    plotted: dict[tuple[int, int], PositionedAircraft] = {}
    for item in positioned:
        aircraft = item.aircraft
        if not options.ground and aircraft.ground:
            continue
        distance_nm = range_nm_from_km(item.distance_km)
        point = project_polar(
            item.bearing_deg,
            distance_nm,
            options.range_nm,
            layout.center_x,
            layout.center_y,
            layout.radar_width / 2 - 2,
            layout.radar_height / 2 - 1,
        )
        if not point.in_range or not (
            layout.radar_x < point.x < layout.radar_x + layout.radar_width - 1
            and layout.radar_y < point.y < layout.radar_y + layout.radar_height - 1
        ):
            continue
        previous = plotted.get((point.x, point.y))
        if (
            previous is not None
            and previous.aircraft.icao != options.selected_icao
            and previous.aircraft.emergency
            and not aircraft.emergency
        ):
            continue
        plotted[(point.x, point.y)] = item
    for (x, y), item in plotted.items():
        if (x, y) == (layout.center_x, layout.center_y):
            continue
        aircraft = item.aircraft
        selected = aircraft.icao == options.selected_icao
        symbol = (
            syms["emergency"]
            if aircraft.emergency and aircraft.emergency.lower() not in {"none", "-"}
            else syms["ground"]
            if aircraft.ground
            else syms["aircraft"]
        )
        buffer.set_cell(
            x,
            y,
            _cell(
                symbol,
                bold=selected or bool(aircraft.emergency),
                inverse=selected,
                foreground=1 if aircraft.emergency else 6,
            ),
        )
        label = _label_for(item, options.label)
        if label:
            for dx, dy in ((1, 0), (-len(label), 0), (0, 1), (0, -1)):
                lx, ly = x + dx, y + dy
                if (
                    layout.radar_x < lx < layout.radar_x + layout.radar_width - 1
                    and layout.radar_y < ly < layout.radar_y + layout.radar_height - 1
                ):
                    if all(
                        buffer.get_cell(lx + index, ly).char in {" ", syms["ring"]}
                        for index in range(min(len(label), width - lx))
                    ):
                        buffer.clipped_text(
                            lx, ly, label, layout.radar_x + layout.radar_width - 1 - lx
                        )
                        break
    buffer.clipped_text(
        2,
        layout.list_y,
        "CALL      ALT      SPD   HDG   DIST   V/S   AGE",
        max(0, width - 4),
    )
    for index, item in enumerate(
        positioned[: max(0, layout.status_y - layout.list_y - 1)]
    ):
        aircraft = item.aircraft
        alt = (
            "GROUND"
            if aircraft.ground
            else str(aircraft.altitude_baro_ft or aircraft.altitude_geom_ft or "-")
        )
        speed = (
            "-"
            if aircraft.ground_speed_kt is None
            else f"{aircraft.ground_speed_kt:.0f}"
        )
        heading = (
            "-" if aircraft.track_deg is None else f"{aircraft.track_deg % 360:03.0f}"
        )
        distance = (
            f"{range_nm_from_km(item.distance_km):.1f}nm"
            if options.units == "aviation"
            else f"{item.distance_km:.1f}km"
        )
        rate = (
            "-"
            if aircraft.vertical_rate_fpm is None
            else f"{aircraft.vertical_rate_fpm:+d}"
        )
        age = (
            "-"
            if aircraft.seen_pos_seconds is None
            else f"{aircraft.seen_pos_seconds:.0f}s"
        )
        row = (
            f"{(aircraft.callsign or aircraft.icao)[:8]:<8} {alt:>7} "
            f"{speed:>5} {heading:>5} {distance:>6} {rate:>5} {age:>4}"
        )
        buffer.clipped_text(2, layout.list_y + 1 + index, row, max(0, width - 4))
    parts = [f"Rng {options.range_nm:.0f}nm", f"{len(positioned)} ac"]
    if options.status:
        parts.append(options.status)
    parts.append("+/- range")
    parts.append("q quit")
    parts.append("? help")
    buffer.clipped_text(2, layout.status_y, " | ".join(parts), max(0, width - 4))
    return buffer
