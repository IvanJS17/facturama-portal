"""Report service layer."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from src.models import PortalDatabase, to_dict


class ReportService:
    """Build aggregated reports for portal analytics."""

    def __init__(self, database: PortalDatabase):
        self.database = database

    def build_report(self, issuer_id: int, report_type: str, params: dict[str, Any]) -> dict[str, Any]:
        issuer = to_dict(self.database.get_issuer(issuer_id))
        if issuer is None:
            raise ValueError("Issuer not found")

        normalized_type = (report_type or "custom").strip().lower()
        if normalized_type == "comparative":
            return self._build_comparative_report(issuer, params)
        if normalized_type == "emisor":
            return self._build_emisor_report(issuer, params)

        start_date, end_date = self._resolve_period(normalized_type, params)
        cfdi_rows = self.database.get_cfdis_by_period(issuer_id, start_date, end_date)
        cfdis = [
            {
                "id": row["id"],
                "uuid": row["uuid"],
                "serie": row["serie"],
                "folio": row["folio"],
                "recipient_name": row["recipient_name"],
                "client_name": row["client_name"],
                "total": float(row["total"] or 0),
                "status": row["status"],
                "created_at": row["created_at"],
                "raw_payload": row["raw_payload"],
            }
            for row in cfdi_rows
        ]

        if normalized_type == "product" and params.get("product_id"):
            product_id = int(params["product_id"])
            allowed_cfdi_ids = self._find_cfdi_ids_by_product(issuer_id, product_id, start_date, end_date)
            cfdis = [cfdi for cfdi in cfdis if cfdi["id"] in allowed_cfdi_ids]
        if normalized_type == "client" and params.get("client_id"):
            client_id = int(params["client_id"])
            cfdis = self._filter_cfdis_by_client(cfdis, issuer_id, client_id)

        summary = self.calculate_summary(issuer_id, cfdis)
        summary["start_date"] = start_date
        summary["end_date"] = end_date

        by_product = [dict(row) for row in self.database.get_product_breakdown(issuer_id, start_date, end_date)]
        by_client = [dict(row) for row in self.database.get_client_breakdown(issuer_id, start_date, end_date)]
        monthly_trend = self._monthly_trend_for_period(issuer_id, start_date, end_date)

        if normalized_type == "product" and params.get("product_id"):
            target = int(params["product_id"])
            product = to_dict(self.database.get_product_for_issuer(target, issuer_id))
            if product:
                by_product = [row for row in by_product if row["product_name"] == product["name"]]
        if normalized_type == "client" and params.get("client_id"):
            target_client = to_dict(self.database.get_client_for_issuer(int(params["client_id"]), issuer_id))
            if target_client:
                by_client = [row for row in by_client if row["client_name"] == target_client["legal_name"]]

        clean_cfdis = [{k: v for k, v in row.items() if k != "raw_payload"} for row in cfdis]

        return {
            "issuer": {
                "id": issuer["id"],
                "legal_name": issuer["legal_name"],
                "rfc": issuer["rfc"],
            },
            "report_type": normalized_type,
            "params": params,
            "summary": summary,
            "cfdis": clean_cfdis,
            "by_product": by_product,
            "by_client": by_client,
            "monthly_trend": monthly_trend,
        }

    def calculate_summary(self, issuer_id: int, cfdis: list[dict[str, Any]]) -> dict[str, Any]:
        cfdi_ids = [int(cfdi["id"]) for cfdi in cfdis]
        subtotal_by_cfdi: dict[int, float] = defaultdict(float)
        iva_by_cfdi: dict[int, float] = defaultdict(float)
        total_by_cfdi: dict[int, float] = {int(cfdi["id"]): float(cfdi.get("total") or 0) for cfdi in cfdis}

        if cfdi_ids:
            placeholders = ",".join("?" for _ in cfdi_ids)
            with self.database.connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT cfdi_id, COALESCE(SUM(subtotal), 0) AS subtotal, COALESCE(SUM(total), 0) AS total
                    FROM cfdi_items
                    WHERE issuer_id = ? AND cfdi_id IN ({placeholders})
                    GROUP BY cfdi_id
                    """,
                    [issuer_id, *cfdi_ids],
                ).fetchall()
            for row in rows:
                cfdi_id = int(row["cfdi_id"])
                subtotal_by_cfdi[cfdi_id] = float(row["subtotal"] or 0)
                item_total = float(row["total"] or 0)
                if item_total >= subtotal_by_cfdi[cfdi_id]:
                    iva_by_cfdi[cfdi_id] = item_total - subtotal_by_cfdi[cfdi_id]
                else:
                    iva_by_cfdi[cfdi_id] = (total_by_cfdi.get(cfdi_id, item_total) / 1.16) * 0.16

        subtotal = 0.0
        iva = 0.0
        cancelled = 0
        total = 0.0
        for cfdi in cfdis:
            cfdi_id = int(cfdi["id"])
            cfdi_total = float(cfdi.get("total") or 0)
            total += cfdi_total
            if str(cfdi.get("status", "")).lower() == "cancelled":
                cancelled += 1

            computed_subtotal = subtotal_by_cfdi.get(cfdi_id, 0.0)
            computed_iva = iva_by_cfdi.get(cfdi_id, 0.0)
            if computed_subtotal <= 0:
                computed_subtotal = cfdi_total / 1.16 if cfdi_total else 0
            payload_iva = self._extract_iva_from_payload(cfdi.get("raw_payload"))
            if payload_iva is not None:
                computed_iva = payload_iva
            elif computed_iva <= 0 and cfdi_total:
                computed_iva = (cfdi_total / 1.16) * 0.16

            subtotal += computed_subtotal
            iva += computed_iva

        return {
            "total_cfdis": len(cfdis),
            "subtotal": round(subtotal, 2),
            "iva": round(iva, 2),
            "total": round(total, 2),
            "cancelled": cancelled,
        }

    def _extract_iva_from_payload(self, raw_payload: Any) -> float | None:
        if not raw_payload:
            return None
        payload_obj: dict[str, Any]
        if isinstance(raw_payload, str):
            try:
                payload_obj = json.loads(raw_payload)
            except json.JSONDecodeError:
                return None
        elif isinstance(raw_payload, dict):
            payload_obj = raw_payload
        else:
            return None

        complement = payload_obj.get("Complement") or payload_obj.get("complement") or {}
        taxes = complement.get("Taxes") or complement.get("taxes") or {}
        transferred = taxes.get("Transferred") or taxes.get("transferred") or []
        tax_total = 0.0
        found = False
        for tax in transferred:
            if not isinstance(tax, dict):
                continue
            raw_tax_name = str(tax.get("Name") or tax.get("name") or tax.get("Tax") or "").upper()
            if raw_tax_name and "IVA" not in raw_tax_name and raw_tax_name != "002":
                continue
            amount = tax.get("Total")
            if amount is None:
                amount = tax.get("Amount")
            try:
                tax_total += float(amount or 0)
                found = True
            except (TypeError, ValueError):
                continue
        return tax_total if found else None

    def _resolve_period(self, report_type: str, params: dict[str, Any]) -> tuple[str, str]:
        if report_type == "monthly":
            year = int(params["year"])
            month = int(params["month"])
            start = date(year, month, 1)
            end = self._month_end(start)
            return start.isoformat(), end.isoformat()
        if report_type == "weekly":
            year = int(params["year"])
            week = int(params["week"])
            start = date.fromisocalendar(year, week, 1)
            end = date.fromisocalendar(year, week, 7)
            return start.isoformat(), end.isoformat()
        if report_type == "yearly":
            year = int(params["year"])
            return date(year, 1, 1).isoformat(), date(year, 12, 31).isoformat()
        if report_type in {"product", "client"}:
            start = params.get("start")
            end = params.get("end")
            if start and end:
                return str(start), str(end)
            today = datetime.utcnow().date()
            return date(today.year, 1, 1).isoformat(), today.isoformat()
        if report_type == "custom":
            return str(params["start"]), str(params["end"])
        raise ValueError("Unsupported report type")

    def _build_comparative_report(self, issuer: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        year = int(params["year"])
        month_a = int(params["month_a"])
        month_b = int(params["month_b"])

        start_a = date(year, month_a, 1)
        end_a = self._month_end(start_a)
        start_b = date(year, month_b, 1)
        end_b = self._month_end(start_b)

        cfdis_a = [dict(row) for row in self.database.get_cfdis_by_period(issuer["id"], start_a.isoformat(), end_a.isoformat())]
        cfdis_b = [dict(row) for row in self.database.get_cfdis_by_period(issuer["id"], start_b.isoformat(), end_b.isoformat())]

        summary_a = self.calculate_summary(issuer["id"], cfdis_a)
        summary_b = self.calculate_summary(issuer["id"], cfdis_b)
        summary_a["start_date"] = start_a.isoformat()
        summary_a["end_date"] = end_a.isoformat()
        summary_b["start_date"] = start_b.isoformat()
        summary_b["end_date"] = end_b.isoformat()

        deltas = {
            "total_cfdis": summary_b["total_cfdis"] - summary_a["total_cfdis"],
            "subtotal": round(summary_b["subtotal"] - summary_a["subtotal"], 2),
            "iva": round(summary_b["iva"] - summary_a["iva"], 2),
            "total": round(summary_b["total"] - summary_a["total"], 2),
            "cancelled": summary_b["cancelled"] - summary_a["cancelled"],
        }

        return {
            "issuer": {"id": issuer["id"], "legal_name": issuer["legal_name"], "rfc": issuer["rfc"]},
            "report_type": "comparative",
            "params": params,
            "summary": {
                "summary_a": summary_a,
                "summary_b": summary_b,
                "deltas": deltas,
            },
            "cfdis": [],
            "by_product": [],
            "by_client": [],
            "monthly_trend": [],
        }

    def _month_end(self, month_start: date) -> date:
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return next_month - timedelta(days=1)

    def _monthly_trend_for_period(self, issuer_id: int, start_date: str, end_date: str) -> list[dict[str, Any]]:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        by_month: dict[str, float] = defaultdict(float)
        cfdis = self.database.get_cfdis_by_period(issuer_id, start_date, end_date)
        for row in cfdis:
            month = str(row["created_at"])[:7]
            by_month[month] += float(row["total"] or 0)
        return [{"month": month, "total": round(by_month[month], 2)} for month in sorted(by_month) if start <= date.fromisoformat(f"{month}-01") <= end]

    def _find_cfdi_ids_by_product(self, issuer_id: int, product_id: int, start_date: str, end_date: str) -> set[int]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT ci.cfdi_id
                FROM cfdi_items ci
                JOIN cfdis c ON c.id = ci.cfdi_id
                WHERE c.issuer_id = ?
                  AND ci.issuer_id = ?
                  AND ci.product_id = ?
                  AND date(c.created_at) >= date(?)
                  AND date(c.created_at) <= date(?)
                """,
                (issuer_id, issuer_id, product_id, start_date, end_date),
            ).fetchall()
        return {int(row["cfdi_id"]) for row in rows}

    def _filter_cfdis_by_client(self, cfdis: list[dict[str, Any]], issuer_id: int, client_id: int) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT legal_name FROM clients WHERE id = ? AND issuer_id = ?",
                (client_id, issuer_id),
            ).fetchone()
        if row is None:
            return []
        target_name = row["legal_name"]
        return [cfdi for cfdi in cfdis if cfdi.get("client_name") == target_name]

    def _build_emisor_report(self, issuer: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        year = int(params["year"])
        period_type = params.get("period_type", "monthly")
        quarter = params.get("quarter")

        if period_type == "yearly":
            start = date(year, 1, 1)
            end = date(year, 12, 31)
        elif period_type == "quarterly" and quarter:
            q = int(str(quarter)[-1])
            month_start = (q - 1) * 3 + 1
            month_end = min(q * 3, 12)
            start = date(year, month_start, 1)
            end = date(year, month_end, self._month_end(date(year, month_end, 1)).day)
        else:
            month = int(params.get("month", 1))
            start = date(year, month, 1)
            end = self._month_end(start)

        start_str = start.isoformat()
        end_str = end.isoformat()

        cfdi_rows = self.database.get_cfdis_by_period(issuer["id"], start_str, end_str)
        cfdis = [
            {
                "id": row["id"],
                "uuid": row["uuid"],
                "serie": row["serie"],
                "folio": row["folio"],
                "recipient_name": row["recipient_name"],
                "client_name": row["client_name"],
                "total": float(row["total"] or 0),
                "status": row["status"],
                "created_at": row["created_at"],
                "raw_payload": row["raw_payload"],
            }
            for row in cfdi_rows
        ]

        summary = self.calculate_summary(issuer["id"], cfdis)
        summary["start_date"] = start_str
        summary["end_date"] = end_str

        by_product = [dict(row) for row in self.database.get_product_breakdown(issuer["id"], start_str, end_str)]
        by_client = [dict(row) for row in self.database.get_client_breakdown(issuer["id"], start_str, end_str)]
        monthly_trend = self._monthly_trend_for_period(issuer["id"], start_str, end_str)

        prev_start, prev_end = self._previous_period(start, end)
        prev_cfdis = [
            {
                "id": row["id"],
                "uuid": row["uuid"],
                "serie": row["serie"],
                "folio": row["folio"],
                "recipient_name": row["recipient_name"],
                "client_name": row["client_name"],
                "total": float(row["total"] or 0),
                "status": row["status"],
                "created_at": row["created_at"],
                "raw_payload": row["raw_payload"],
            }
            for row in self.database.get_cfdis_by_period(issuer["id"], prev_start, prev_end)
        ]
        previous_summary = self.calculate_summary(issuer["id"], prev_cfdis)

        top_products = sorted(by_product, key=lambda x: float(x.get("total", 0)), reverse=True)[:5]
        top_clients = sorted(by_client, key=lambda x: float(x.get("total", 0)), reverse=True)[:5]

        total_cfdis = summary.get("total_cfdis", 0)
        summary["avg_per_cfdi"] = round(summary["total"] / total_cfdis, 2) if total_cfdis > 0 else 0.0

        clean_cfdis = [{k: v for k, v in row.items() if k != "raw_payload"} for row in cfdis]

        period_label = self._emisor_period_label(year, params)

        return {
            "issuer": {
                "id": issuer["id"],
                "legal_name": issuer["legal_name"],
                "rfc": issuer["rfc"],
            },
            "report_type": "emisor",
            "params": params,
            "summary": summary,
            "cfdis": clean_cfdis,
            "by_product": by_product,
            "by_client": by_client,
            "monthly_trend": monthly_trend,
            "top_products": top_products,
            "top_clients": top_clients,
            "previous_summary": previous_summary,
            "period_label": period_label,
        }

    def _previous_period(self, start: date, end: date) -> tuple[str, str]:
        delta = end - start
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - delta
        return prev_start.isoformat(), prev_end.isoformat()

    def _emisor_period_label(self, year: int, params: dict[str, Any]) -> str:
        period_type = params.get("period_type", "monthly")
        if period_type == "yearly":
            return str(year)
        if period_type == "quarterly":
            quarter = int(str(params.get("quarter", "Q1"))[-1])
            return f"Q{quarter} {year}"
        month = int(params.get("month", 1))
        from datetime import datetime as dt
        return f"{dt(year, month, 1):%B %Y}"
