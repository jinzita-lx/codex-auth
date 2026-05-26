from .colors import Palette
from .usage import UsageSummary


def print_profile_block(
    palette: Palette,
    marker: str,
    name: str,
    identity: str,
    summary: UsageSummary,
    reset_style: str,
) -> None:
    prefix = palette.text(palette.green + palette.bold, "*") if marker == "*" else " "
    name_color = palette.bold + palette.cyan if marker == "*" else palette.bold
    print(f"{prefix} {palette.text(name_color, name)}")
    print(f"  {palette.text(palette.dim, 'account:')} {identity}")
    print(f"  {palette.text(palette.dim, 'status:')}  {palette.text(palette.status(summary.status), summary.status)}")
    if summary.plan != "-":
        print(f"  {palette.text(palette.dim, 'plan:')}    {palette.text(palette.cyan, summary.plan)}")

    if summary.five_h_used != "-" or summary.seven_d_used != "-":
        five_reset = summary.five_h_reset_full if reset_style == "full" else summary.five_h_reset_short
        seven_reset = summary.seven_d_reset_full if reset_style == "full" else summary.seven_d_reset_short
        print(f"  {palette.text(palette.dim, 'usage:')}")
        _print_usage_row(palette, "5h", summary.five_h_used, summary.five_h_left, five_reset)
        _print_usage_row(palette, "7d", summary.seven_d_used, summary.seven_d_left, seven_reset)

    if summary.credits_balance != "-" or summary.reset_credits != "-":
        print(
            f"  {palette.text(palette.dim, 'credits:')} "
            f"balance={palette.text(palette.yellow, summary.credits_balance)}, "
            f"reset-credits={palette.text(palette.yellow, summary.reset_credits)}"
        )


def _print_usage_row(palette: Palette, label: str, used: str, left: str, reset: str) -> None:
    used_field = palette.text(palette.dim, f"{used:>4}")
    left_field = palette.text(palette.percent_left(left), f"{left:>4}")
    print(
        f"    {palette.text(palette.blue, f'{label:<3}')} "
        f"{used_field} used  {left_field} left  "
        f"{palette.text(palette.dim, 'resets')} {palette.text(palette.cyan, reset)}"
    )


def print_summary_header(palette: Palette) -> None:
    print(
        " ".join(
            [
                palette.text(palette.dim, f"{'profile':<18}"),
                palette.text(palette.dim, f"{'status':<9}"),
                palette.text(palette.dim, f"{'plan':<7}"),
                palette.text(palette.dim, f"{'5h':<5}"),
                palette.text(palette.dim, f"{'7d':<5}"),
                palette.text(palette.dim, "account"),
            ]
        )
    )


def print_summary_line(
    palette: Palette,
    marker: str,
    name: str,
    identity: str,
    summary: UsageSummary,
) -> None:
    profile = f"{marker} {name}"
    profile_field = f"{profile:<18}"
    if marker == "*":
        profile_field = palette.text(palette.bold + palette.cyan, profile_field)
    print(
        " ".join(
            [
                profile_field,
                palette.text(palette.status(summary.status), f"{summary.status:<9}"),
                palette.text(palette.cyan if summary.plan != "-" else "", f"{summary.plan:<7}"),
                palette.text(palette.percent_left(summary.five_h_left), f"{summary.five_h_left:<5}"),
                palette.text(palette.percent_left(summary.seven_d_left), f"{summary.seven_d_left:<5}"),
                identity,
            ]
        )
    )
