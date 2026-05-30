"""The stub extractor must emit the new fields (items / cost_center / category)."""

from __future__ import annotations

from apps.api.services.ingestion import canonical_text_from_mapping

from packages.agents.stub_extractor import extract_from_text


def test_stub_extracts_cost_center_and_category() -> None:
    text = (
        "Fornecedor: Acme Ltda\nCNPJ: 12.345.678/0001-90\nNumero: 778899\n"
        "Total: R$ 5.000,00\nCentro de Custo: CC-100\nCategoria: legal\n"
    )
    out = extract_from_text(text)
    assert out.cost_center is not None and out.cost_center.value == "CC-100"
    assert out.category is not None and str(out.category.value).strip() == "legal"


def test_stub_extracts_line_items() -> None:
    text = (
        "Valor Total: R$ 5.000,00\n"
        "Item: Widget A | Qtd: 2 | Unit: R$ 1.000,00 | Total: R$ 2.000,00\n"
        "Item: Widget B | Qtd: 3 | Unit: R$ 1.000,00 | Total: R$ 3.000,00\n"
    )
    out = extract_from_text(text)
    assert len(out.items) == 2
    assert sum(i.line_total or 0 for i in out.items) == 5000.0


def test_canonical_text_maps_known_keys() -> None:
    text = canonical_text_from_mapping(
        {"supplier": "Acme", "cnpj": "12.345.678/0001-90", "total": "5000.00", "blank": ""}
    )
    assert "Fornecedor: Acme" in text
    assert "CNPJ: 12.345.678/0001-90" in text
    assert "Total: 5000.00" in text
    assert "blank" not in text  # empty values are skipped


def test_erp_record_flows_through_extractor() -> None:
    # An ERP payload serialised to canonical text must extract back to the same fields.
    text = canonical_text_from_mapping(
        {
            "fornecedor": "Beta SA",
            "cnpj": "11.222.333/0001-44",
            "numero": "990011",
            "total": "1.234,56",
        }
    )
    out = extract_from_text(text)
    assert out.tax_id_cnpj is not None and out.tax_id_cnpj.value == "11.222.333/0001-44"
    assert out.total_amount is not None and out.total_amount.value == 1234.56
