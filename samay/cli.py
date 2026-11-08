"""Stateless command line: birth data in, chart text out. Never touches the user store."""
from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import UTC, datetime

import click

from . import service
from .engine.errors import SamayError
from .engine.profiles import DEFAULT_PROFILE
from .models import BirthInput, NeedsDisambiguation, ResolvedBirth
from .render.text import render_chart, render_dasha, render_options, render_today

EXIT_ERROR, EXIT_AMBIGUOUS = 1, 2


def birth_options(fn: Callable) -> Callable:
    options = [
        click.option("--date", "date_text", required=True, help="Birth date, YYYY-MM-DD."),
        click.option("--time", "time_text", required=True, help="Local clock time at the birthplace, HH:MM."),
        click.option("--place", "place_text", required=True, help='Birthplace, e.g. "Pune" or "Pune, IN".'),
        click.option("--choice", "place_choice", help="Place id from a previous ambiguity listing."),
        click.option("--fold", type=click.IntRange(0, 1), help="0 = first, 1 = second occurrence of a repeated time."),
        click.option("--profile", default=DEFAULT_PROFILE, show_default=True, help="Tradition profile."),
    ]
    for option in reversed(options):
        fn = option(fn)
    return fn


def _resolve(**kw) -> ResolvedBirth:
    try:
        result = service.resolve_birth(BirthInput(**kw))
    except SamayError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(EXIT_ERROR)
    if isinstance(result, NeedsDisambiguation):
        flag = "--choice" if result.kind == "place" else "--fold"
        click.echo(f"ambiguous {result.kind}; rerun with {flag}:", err=True)
        for i, (option, line) in enumerate(zip(result.options, render_options(result))):
            value = option.id if result.kind == "place" else i
            click.echo(f"  {flag} {value}   {line}", err=True)
        sys.exit(EXIT_AMBIGUOUS)
    return result


def _run(fn: Callable[[], str]) -> None:
    try:
        click.echo(fn())
    except SamayError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(EXIT_ERROR)


@click.group()
def cli() -> None:
    """samay — sidereal Jyotish charts from bundled offline data."""


@cli.command()
@birth_options
def chart(**kw) -> None:
    """Birth chart, yogas and provenance."""
    birth = _resolve(**kw)
    _run(lambda: render_chart(service.natal_report(birth)))


@cli.command()
@birth_options
@click.option("--now", type=click.DateTime(), help="Moment to mark as now (UTC). Default: current time.")
def dasha(now: datetime | None, **kw) -> None:
    """Vimshottari mahadashas."""
    birth = _resolve(**kw)
    when = now.replace(tzinfo=UTC) if now else datetime.now(UTC)
    _run(lambda: render_dasha(service.natal_report(birth), when))


@cli.command()
@birth_options
@click.option("--now", type=click.DateTime(), help="Moment for transits (UTC). Default: current time.")
def today(now: datetime | None, **kw) -> None:
    """Transits relative to the natal Moon."""
    birth = _resolve(**kw)
    when = now.replace(tzinfo=UTC) if now else datetime.now(UTC)
    _run(lambda: render_today(service.today_report(birth, when)))


@cli.command("data-info")
@click.option("--profile", default=DEFAULT_PROFILE, show_default=True)
def data_info(profile: str) -> None:
    """Versions of every data source a reading depends on."""
    _run(lambda: "\n".join(f"{k}: {v}" for k, v in vars(service.data_info(profile)).items()))
