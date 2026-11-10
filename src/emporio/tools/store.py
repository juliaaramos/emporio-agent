"""Informações da loja e horário de funcionamento (§2), com feriados nacionais e de MS."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import holidays

from ..config import STORE, TZ, reference_now

WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


def hours_for(d: date) -> tuple[time, time] | None:
    if d in holidays.country_holidays("BR", subdiv="MS", years=d.year):
        return None
    if d.weekday() < 5:
        return time(9), time(18)
    if d.weekday() == 5:
        return time(9), time(13)
    return None


def status_at(now: datetime) -> dict:
    today_hours = hours_for(now.date())
    aberta = bool(today_hours and today_hours[0] <= now.time() < today_hours[1])
    out = {
        "agora": f"{WEEKDAYS[now.weekday()]}, {now:%d/%m/%Y %H:%M} (horário de Campo Grande)",
        "aberta_agora": aberta,
    }
    feriado = holidays.country_holidays("BR", subdiv="MS", years=now.year).get(now.date())
    if feriado:
        out["feriado_hoje"] = feriado
    if aberta:
        out["fecha_hoje_as"] = today_hours[1].strftime("%H:%M")
    else:
        for i in range(0, 15):
            d = now.date() + timedelta(days=i)
            h = hours_for(d)
            if h and (i > 0 or now.time() < h[0]):
                quando = "hoje" if i == 0 else ("amanhã" if i == 1 else WEEKDAYS[d.weekday()])
                out["reabre"] = f"{quando}, {d:%d/%m}, às {h[0]:%H:%M}"
                break
    return out


def info_loja() -> dict:
    return {
        **STORE,
        "horarios": {
            "segunda_a_sexta": "09:00 às 18:00",
            "sabado": "09:00 às 13:00",
            "domingo_e_feriados": "fechado",
            "observacao": "O WhatsApp segue o mesmo horário. Em datas especiais o horário pode ser estendido (§2).",
        },
        **status_at(reference_now().astimezone(TZ)),
    }
