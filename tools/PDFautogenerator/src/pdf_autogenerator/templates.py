from __future__ import annotations

from random import Random
from typing import Any

from .content import (
    choose,
    choose_many,
    join_sentences,
    make_content_fingerprint,
    make_course_line,
    make_date_text,
    make_department_line,
    make_person_name,
    make_reference_id,
    sentence_paragraph,
)
from .models import BlockSpec, DocumentPlan, RegionPlan, RegionSpec, TemplateDefinition, VariantChoices


def _margin_points(variant: VariantChoices) -> float:
    return {"0.5in": 36.0, "0.75in": 54.0, "1.0in": 72.0}[variant.margin_preset]


def _base_regions(
    variant: VariantChoices,
    page_size: tuple[float, float],
    *,
    split_columns: bool = False,
) -> dict[str, RegionSpec]:
    width, height = page_size
    margin = _margin_points(variant)
    header_height = 68.0 if variant.has_header else 0.0
    footer_height = 30.0 if variant.has_footer else 0.0
    top_y = height - margin
    bottom_y = margin
    content_top = top_y - header_height
    content_bottom = bottom_y + footer_height
    content_height = max(content_top - content_bottom, 50.0)
    usable_width = width - (2 * margin)
    regions: dict[str, RegionSpec] = {}
    if variant.has_header:
        regions["header"] = RegionSpec(
            name="header",
            x=margin,
            y=top_y - header_height,
            width=usable_width,
            height=header_height - 8.0,
            padding=4.0,
        )
    if split_columns:
        gutter = 18.0
        column_width = (usable_width - gutter) / 2
        regions["left"] = RegionSpec(
            name="left",
            x=margin,
            y=content_bottom,
            width=column_width,
            height=content_height,
            padding=4.0,
        )
        regions["right"] = RegionSpec(
            name="right",
            x=margin + column_width + gutter,
            y=content_bottom,
            width=column_width,
            height=content_height,
            padding=4.0,
        )
    else:
        regions["main"] = RegionSpec(
            name="main",
            x=margin,
            y=content_bottom,
            width=usable_width,
            height=content_height,
            padding=4.0,
        )
    if variant.has_footer:
        regions["footer"] = RegionSpec(
            name="footer",
            x=margin,
            y=bottom_y - 2.0,
            width=usable_width,
            height=footer_height,
            padding=2.0,
        )
    return regions


def _form_regions(variant: VariantChoices, page_size: tuple[float, float]) -> dict[str, RegionSpec]:
    width, height = page_size
    margin = _margin_points(variant)
    header_height = 64.0 if variant.has_header else 0.0
    footer_height = 40.0 if variant.has_footer else 0.0
    usable_width = width - (2 * margin)
    top_y = height - margin
    bottom_y = margin
    content_top = top_y - header_height
    content_bottom = bottom_y + footer_height
    content_height = max(content_top - content_bottom, 180.0)
    field_height = 192.0
    signature_height = 72.0
    checklist_height = max(content_height - field_height - signature_height, 90.0)
    regions: dict[str, RegionSpec] = {}
    if variant.has_header:
        regions["header"] = RegionSpec("header", margin, top_y - header_height, usable_width, header_height)
    regions["fields"] = RegionSpec(
        "fields",
        margin,
        content_bottom + checklist_height + signature_height,
        usable_width,
        field_height,
        border=True,
        padding=6.0,
    )
    regions["checklist"] = RegionSpec(
        "checklist",
        margin,
        content_bottom + signature_height,
        usable_width,
        checklist_height,
        border=True,
        padding=6.0,
    )
    regions["signature"] = RegionSpec(
        "signature",
        margin,
        content_bottom,
        usable_width,
        signature_height,
        border=True,
        padding=6.0,
    )
    if variant.has_footer:
        regions["footer"] = RegionSpec("footer", margin, bottom_y - 2.0, usable_width, footer_height)
    return regions


def _invoice_regions(variant: VariantChoices, page_size: tuple[float, float]) -> dict[str, RegionSpec]:
    width, height = page_size
    margin = _margin_points(variant)
    usable_width = width - (2 * margin)
    header_height = 70.0
    footer_height = 24.0 if variant.has_footer else 0.0
    top_y = height - margin
    bottom_y = margin
    content_top = top_y - header_height
    content_bottom = bottom_y + footer_height
    summary_height = 88.0
    table_height = 200.0 if variant.density_preset != "dense" else 220.0
    totals_height = 88.0
    note_height = max(content_top - content_bottom - summary_height - table_height - totals_height, 28.0)
    regions = {
        "header": RegionSpec("header", margin, top_y - header_height, usable_width, header_height, padding=4.0),
        "summary": RegionSpec("summary", margin, content_bottom + table_height + totals_height + note_height, usable_width, summary_height, padding=4.0),
        "table": RegionSpec("table", margin, content_bottom + totals_height + note_height, usable_width, table_height, padding=4.0, border=True),
        "totals": RegionSpec("totals", margin, content_bottom + note_height, usable_width, totals_height, padding=4.0, border=True),
        "notes": RegionSpec("notes", margin, content_bottom, usable_width, note_height, padding=4.0),
    }
    if variant.has_footer:
        regions["footer"] = RegionSpec("footer", margin, bottom_y - 2.0, usable_width, footer_height)
    return regions


def _title_header(title: str, line: str, *, bold_title: bool = True) -> list[BlockSpec]:
    return [
        BlockSpec(kind="title", text=title, bold=bold_title),
        BlockSpec(kind="meta_line", text=line),
        BlockSpec(kind="rule"),
    ]


def _main_title_blocks(title: str, line: str, *, bold_title: bool = True) -> list[BlockSpec]:
    return [
        BlockSpec(kind="title", text=title, bold=bold_title),
        BlockSpec(kind="meta_line", text=line),
    ]


def _footer_blocks(rng: Random, bank: dict[str, Any], variant: VariantChoices, footer_text: str) -> list[BlockSpec]:
    if not variant.has_footer:
        return []
    blocks = [BlockSpec(kind="footer", text=footer_text, small=True, align="center")]
    if variant.has_small_text:
        blocks.append(
            BlockSpec(
                kind="footer",
                text=choose(rng, bank["common"]["small_notes"]),
                small=True,
                align="center",
            )
        )
    return blocks


def _academic_composer(
    rng: Random,
    variant: VariantChoices,
    bank: dict[str, Any],
    definition: TemplateDefinition,
) -> dict[str, list[BlockSpec]]:
    academic = bank["academic"]
    title = choose(rng, academic["titles"])
    course_line = make_course_line(rng, bank)
    header_blocks = _title_header(title, course_line, bold_title=rng.random() < 0.7)
    intro_blocks = [] if variant.has_header else _main_title_blocks(title, course_line, bold_title=True)
    question_count = 3 + bank["density_level"]
    questions = choose_many(rng, academic["questions"], question_count)
    reading_label = choose(rng, academic["reading_labels"])
    main_blocks = intro_blocks + [
        BlockSpec(kind="section_heading", text=choose(rng, academic["section_titles"]), bold=rng.random() < 0.6),
        BlockSpec(kind="paragraph", text=sentence_paragraph(rng, academic["paragraphs"], 2, 3)),
        BlockSpec(kind="section_heading", text=reading_label, bold=rng.random() < 0.6),
        BlockSpec(kind="bullet_list", items=choose_many(rng, academic["paragraphs"], 2 + bank["density_level"])),
        BlockSpec(kind="section_heading", text=choose(rng, academic["section_titles"]), bold=True),
        BlockSpec(kind="numbered_list", items=questions),
        BlockSpec(kind="paragraph", text=choose(rng, academic["office_hours"])),
    ]
    if definition.template_id == "practice-worksheet":
        main_blocks.extend(
            [
                BlockSpec(kind="section_heading", text="Short Responses", bold=True),
                BlockSpec(
                    kind="labeled_fields",
                    items=[f"Response {index + 1}" for index in range(2 + bank["density_level"])],
                ),
            ]
        )
    elif definition.template_id == "reading-question-sheet":
        main_blocks.insert(
            4,
            BlockSpec(
                kind="paragraph",
                text="Complete the questions before class and bring a printed copy for discussion.",
            ),
        )

    footer = _footer_blocks(rng, bank, variant, choose(rng, ["Course handout", "Class copy", "Discussion copy"]))
    blocks_by_region = {"main": main_blocks, "footer": footer}
    if variant.column_mode == "double":
        split_point = max(len(main_blocks) // 2, 3)
        blocks_by_region = {"left": main_blocks[:split_point], "right": main_blocks[split_point:], "footer": footer}
    if variant.has_header:
        blocks_by_region["header"] = header_blocks
    blocks_by_region["_fingerprint"] = [
        BlockSpec(
            kind="fingerprint",
            metadata={
                "title": title,
                "course_line": course_line,
                "questions": questions,
                "layout_variant": variant.layout_variant,
                "template_id": definition.template_id,
            },
        )
    ]
    return blocks_by_region


def _business_composer(
    rng: Random,
    variant: VariantChoices,
    bank: dict[str, Any],
    definition: TemplateDefinition,
) -> dict[str, list[BlockSpec]]:
    business = bank["business"]
    company = choose(rng, bank["common"]["companies"])
    title = choose(rng, business["titles"])
    subject = choose(rng, business["subjects"])
    author = make_person_name(rng, bank)
    header_line = f"{company} | {subject} | {make_date_text(rng, bank)}"
    header_blocks = _title_header(title, header_line, bold_title=True)
    intro = [] if variant.has_header else _main_title_blocks(title, header_line, bold_title=True)
    bullets = choose_many(rng, business["bullet_points"], 3 + bank["density_level"])
    sections = choose_many(rng, business["section_titles"], 3)
    body = intro + [
        BlockSpec(kind="paragraph", text=f"Prepared by {author} for {choose(rng, bank['common']['departments'])}."),
        BlockSpec(kind="section_heading", text=sections[0], bold=rng.random() < 0.7),
        BlockSpec(kind="paragraph", text=sentence_paragraph(rng, business["paragraphs"], 2, 3)),
        BlockSpec(kind="section_heading", text=sections[1], bold=True),
        BlockSpec(kind="bullet_list", items=bullets),
        BlockSpec(kind="section_heading", text=sections[2], bold=rng.random() < 0.7),
        BlockSpec(kind="paragraph", text=sentence_paragraph(rng, business["paragraphs"], 2, 3)),
        BlockSpec(kind="signature_block", items=[author, "Department Lead"]),
    ]
    if definition.template_id == "status-report":
        body.insert(
            5,
            BlockSpec(
                kind="table",
                columns=["Area", "Status", "Owner"],
                rows=[
                    ["Scheduling", "On Track", make_person_name(rng, bank)],
                    ["Supplies", "In Review", make_person_name(rng, bank)],
                    ["Facilities", "Stable", make_person_name(rng, bank)],
                ],
                boxed=True,
            ),
        )
    footer = _footer_blocks(rng, bank, variant, company)
    blocks_by_region = {"main": body, "footer": footer}
    if variant.column_mode == "double":
        split_point = max(len(body) // 2, 3)
        blocks_by_region = {"left": body[:split_point], "right": body[split_point:], "footer": footer}
    if variant.has_header:
        blocks_by_region["header"] = header_blocks
    blocks_by_region["_fingerprint"] = [
        BlockSpec(
            kind="fingerprint",
            metadata={
                "title": title,
                "company": company,
                "subject": subject,
                "author": author,
                "layout_variant": variant.layout_variant,
                "template_id": definition.template_id,
            },
        )
    ]
    return blocks_by_region


def _form_composer(
    rng: Random,
    variant: VariantChoices,
    bank: dict[str, Any],
    definition: TemplateDefinition,
) -> dict[str, list[BlockSpec]]:
    forms = bank["forms"]
    title = choose(rng, forms["titles"])
    form_code = make_reference_id(rng, "FRM")
    header_line = f"{form_code} | {make_department_line(rng, bank)}"
    header_blocks = _title_header(title, header_line, bold_title=True)
    field_labels = choose_many(rng, forms["field_labels"], 5 + bank["density_level"])
    checkbox_items = choose_many(rng, forms["checkbox_items"], 4 + bank["density_level"])
    fields = [label for label in field_labels if label != "Signature"]
    field_region = [
        BlockSpec(kind="paragraph", text=choose(rng, forms["acknowledgement_lines"])),
        BlockSpec(kind="labeled_fields", items=fields, boxed=True),
    ]
    checklist_region = [
        BlockSpec(kind="section_heading", text="Checklist", bold=True),
        BlockSpec(kind="checkbox_list", items=checkbox_items),
    ]
    if definition.template_id == "intake-worksheet":
        checklist_region.extend(
            [
                BlockSpec(
                    kind="paragraph",
                    text="Use the notes area to record follow-up items or scheduling constraints.",
                ),
                BlockSpec(kind="labeled_fields", items=["Notes"], boxed=True, metadata={"rows": 2}),
            ]
        )
    if definition.template_id == "checklist-form":
        checklist_region.insert(
            1,
            BlockSpec(
                kind="table",
                columns=["Task", "Status"],
                rows=[[item, "Pending"] for item in checkbox_items[: min(4, len(checkbox_items))]],
                boxed=True,
            ),
        )
    signature_region = [
        BlockSpec(kind="signature_block", items=choose_many(rng, forms["signature_labels"], 2)),
        BlockSpec(kind="meta_line", text=f"Completed on {make_date_text(rng, bank)}"),
    ]
    footer = _footer_blocks(rng, bank, variant, choose(rng, ["Administrative form", "Office copy", "Records copy"]))
    blocks_by_region = {
        "fields": field_region,
        "checklist": checklist_region,
        "signature": signature_region,
        "footer": footer,
    }
    if variant.has_header:
        blocks_by_region["header"] = header_blocks
    else:
        field_region[:0] = [BlockSpec(kind="title", text=title, bold=True), BlockSpec(kind="meta_line", text=header_line)]
    blocks_by_region["_fingerprint"] = [
        BlockSpec(
            kind="fingerprint",
            metadata={
                "title": title,
                "header_line": header_line,
                "fields": fields,
                "checks": checkbox_items,
                "layout_variant": variant.layout_variant,
                "template_id": definition.template_id,
            },
        )
    ]
    return blocks_by_region


def _policy_composer(
    rng: Random,
    variant: VariantChoices,
    bank: dict[str, Any],
    definition: TemplateDefinition,
) -> dict[str, list[BlockSpec]]:
    policy = bank["policy"]
    title = choose(rng, policy["titles"])
    header_line = f"{choose(rng, bank['common']['departments'])} | {make_date_text(rng, bank)}"
    header_blocks = _title_header(title, header_line, bold_title=rng.random() < 0.65)
    intro = [] if variant.has_header else _main_title_blocks(title, header_line, bold_title=True)
    sections = choose_many(rng, policy["section_titles"], 3 + (1 if bank["density_level"] > 0 else 0))
    body = intro[:]
    for section in sections:
        body.append(BlockSpec(kind="section_heading", text=section, bold=rng.random() < 0.6))
        body.append(BlockSpec(kind="paragraph", text=sentence_paragraph(rng, policy["paragraphs"], 1, 2)))
    footer = _footer_blocks(rng, bank, variant, choose(rng, policy["footer_lines"]))
    blocks_by_region = {"main": body, "footer": footer}
    if variant.has_header:
        blocks_by_region["header"] = header_blocks
    blocks_by_region["_fingerprint"] = [
        BlockSpec(
            kind="fingerprint",
            metadata={
                "title": title,
                "sections": sections,
                "layout_variant": variant.layout_variant,
                "template_id": definition.template_id,
            },
        )
    ]
    return blocks_by_region


def _invoice_rows(rng: Random, bank: dict[str, Any], count: int) -> tuple[list[list[str]], float]:
    rows: list[list[str]] = []
    total = 0.0
    descriptions = choose_many(rng, bank["invoice"]["item_names"], count)
    for description in descriptions:
        quantity = rng.randint(1, 4)
        unit_price = rng.randint(18, 175) + rng.random()
        amount = quantity * unit_price
        total += amount
        rows.append([description, str(quantity), f"${unit_price:0.2f}", f"${amount:0.2f}"])
    return rows, total


def _invoice_composer(
    rng: Random,
    variant: VariantChoices,
    bank: dict[str, Any],
    definition: TemplateDefinition,
) -> dict[str, list[BlockSpec]]:
    vendor = choose(rng, bank["invoice"]["vendors"])
    invoice_number = make_reference_id(rng, "INV")
    header_blocks = _title_header(vendor, f"{definition.display_name} | {invoice_number}", bold_title=True)
    rows, subtotal = _invoice_rows(rng, bank, 4 + bank["density_level"])
    tax = round(subtotal * 0.08, 2)
    total = subtotal + tax
    blocks_by_region = {
        "header": header_blocks,
        "summary": [
            BlockSpec(kind="meta_line", text=f"Invoice No. {invoice_number}"),
            BlockSpec(kind="meta_line", text=f"Date: {make_date_text(rng, bank)}"),
            BlockSpec(kind="meta_line", text=f"Terms: {choose(rng, bank['invoice']['terms'])}"),
            BlockSpec(kind="meta_line", text=f"Bill To: {choose(rng, bank['common']['departments'])}"),
        ],
        "table": [
            BlockSpec(kind="table", columns=["Description", "Qty", "Unit", "Amount"], rows=rows, boxed=True)
        ],
        "totals": [
            BlockSpec(
                kind="table",
                columns=["Label", "Value"],
                rows=[["Subtotal", f"${subtotal:0.2f}"], ["Tax", f"${tax:0.2f}"], ["Total", f"${total:0.2f}"]],
                boxed=True,
                metadata={"totals": True},
            )
        ],
        "notes": [BlockSpec(kind="paragraph", text=choose(rng, bank["invoice"]["footer_lines"]))],
        "footer": _footer_blocks(rng, bank, variant, choose(rng, ["Billing copy", "Accounts copy", "Receipt copy"])),
        "_fingerprint": [
            BlockSpec(
                kind="fingerprint",
                metadata={
                    "vendor": vendor,
                    "invoice_number": invoice_number,
                    "rows": rows,
                    "total": f"{total:0.2f}",
                    "layout_variant": variant.layout_variant,
                    "template_id": definition.template_id,
                },
            )
        ],
    }
    return blocks_by_region


def _syllabus_composer(
    rng: Random,
    variant: VariantChoices,
    bank: dict[str, Any],
    definition: TemplateDefinition,
) -> dict[str, list[BlockSpec]]:
    syllabus = bank["syllabus"]
    course = choose(rng, syllabus["courses"])
    title = choose(rng, syllabus["titles"])
    instructor = make_person_name(rng, bank)
    header_line = f"{course} | {instructor} | {make_date_text(rng, bank)}"
    header_blocks = _title_header(title, header_line, bold_title=True)
    intro = [] if variant.has_header else _main_title_blocks(title, header_line, bold_title=True)
    grading_labels = choose_many(rng, syllabus["grading_labels"], 3 + bank["density_level"])
    remaining = 100
    grading_rows: list[list[str]] = []
    for index, label in enumerate(grading_labels):
        if index == len(grading_labels) - 1:
            weight = remaining
        else:
            max_weight = max(15, remaining - (len(grading_labels) - index - 1) * 10)
            weight = rng.randint(10, max_weight)
            remaining -= weight
        grading_rows.append([label, f"{weight}%"])
    topics = choose_many(rng, syllabus["schedule_topics"], 4 + bank["density_level"])
    policies = choose_many(rng, syllabus["policies"], 2 + min(bank["density_level"], 1))
    body = intro + [
        BlockSpec(kind="section_heading", text="Course Information", bold=True),
        BlockSpec(kind="paragraph", text=f"Instructor: {instructor}. Office: {choose(rng, bank['common']['locations'])}."),
        BlockSpec(kind="section_heading", text="Grading Breakdown", bold=True),
        BlockSpec(kind="table", columns=["Component", "Weight"], rows=grading_rows, boxed=True),
        BlockSpec(kind="section_heading", text="Policies", bold=rng.random() < 0.7),
        BlockSpec(kind="bullet_list", items=policies),
        BlockSpec(kind="section_heading", text="Schedule", bold=True),
        BlockSpec(kind="table", columns=["Week", "Topic"], rows=[[str(index + 1), topic] for index, topic in enumerate(topics)], boxed=True),
    ]
    footer = _footer_blocks(rng, bank, variant, course)
    blocks_by_region = {"main": body, "footer": footer}
    if variant.column_mode == "double":
        split_point = 4
        blocks_by_region = {"left": body[:split_point], "right": body[split_point:], "footer": footer}
    if variant.has_header:
        blocks_by_region["header"] = header_blocks
    blocks_by_region["_fingerprint"] = [
        BlockSpec(
            kind="fingerprint",
            metadata={
                "title": title,
                "course": course,
                "instructor": instructor,
                "grading": grading_rows,
                "topics": topics,
                "layout_variant": variant.layout_variant,
                "template_id": definition.template_id,
            },
        )
    ]
    return blocks_by_region


TEMPLATES: list[TemplateDefinition] = [
    TemplateDefinition("lecture-handout", "academic_handout", "academic", "Lecture Handout", True, geometry_builder=lambda v, p: _base_regions(v, p, split_columns=v.column_mode == "double"), composer=_academic_composer),
    TemplateDefinition("reading-question-sheet", "academic_handout", "academic", "Reading Question Sheet", True, geometry_builder=lambda v, p: _base_regions(v, p, split_columns=v.column_mode == "double"), composer=_academic_composer),
    TemplateDefinition("practice-worksheet", "academic_handout", "academic", "Practice Worksheet", True, geometry_builder=lambda v, p: _base_regions(v, p, split_columns=v.column_mode == "double"), composer=_academic_composer),
    TemplateDefinition("executive-memo", "business_memo_report", "business", "Executive Memo", geometry_builder=lambda v, p: _base_regions(v, p, split_columns=v.column_mode == "double"), composer=_business_composer),
    TemplateDefinition("status-report", "business_memo_report", "business", "Short Status Report", True, True, False, False, geometry_builder=lambda v, p: _base_regions(v, p, split_columns=v.column_mode == "double"), composer=_business_composer),
    TemplateDefinition("acknowledgement-form", "form_worksheet", "form", "Acknowledgement Form", geometry_builder=_form_regions, composer=_form_composer),
    TemplateDefinition("intake-worksheet", "form_worksheet", "form", "Intake Worksheet", geometry_builder=_form_regions, composer=_form_composer),
    TemplateDefinition("checklist-form", "form_worksheet", "form", "Checklist Form", False, True, False, False, _form_regions, _form_composer),
    TemplateDefinition("administrative-notice", "policy_notice", "policy", "Administrative Notice", geometry_builder=_base_regions, composer=_policy_composer),
    TemplateDefinition("policy-bulletin", "policy_notice", "policy", "Policy Bulletin", geometry_builder=_base_regions, composer=_policy_composer),
    TemplateDefinition("invoice", "invoice_receipt", "invoice", "Invoice", False, True, True, True, _invoice_regions, _invoice_composer),
    TemplateDefinition("itemized-receipt", "invoice_receipt", "invoice", "Itemized Receipt", False, True, True, True, _invoice_regions, _invoice_composer),
    TemplateDefinition("course-syllabus", "syllabus_info", "syllabus", "Course Syllabus", True, True, False, False, geometry_builder=lambda v, p: _base_regions(v, p, split_columns=v.column_mode == "double"), composer=_syllabus_composer),
    TemplateDefinition("program-information-sheet", "syllabus_info", "syllabus", "Program Information Sheet", True, True, False, False, geometry_builder=lambda v, p: _base_regions(v, p, split_columns=v.column_mode == "double"), composer=_syllabus_composer),
]

TEMPLATE_REGISTRY = {template.template_id: template for template in TEMPLATES}


def get_template(template_id: str) -> TemplateDefinition:
    try:
        return TEMPLATE_REGISTRY[template_id]
    except KeyError as exc:
        raise KeyError(f"Unknown template_id: {template_id}") from exc


def resolve_templates(allowlist: list[str] | None = None) -> list[TemplateDefinition]:
    if not allowlist:
        return list(TEMPLATES)
    return [get_template(template_id) for template_id in allowlist]


def templates_for_source(source_type: str) -> list[TemplateDefinition]:
    return [template for template in TEMPLATES if template.source_type == source_type]


def build_document_plan(
    definition: TemplateDefinition,
    variant: VariantChoices,
    bank: dict[str, Any],
    page_size: tuple[float, float],
    rng: Random,
) -> DocumentPlan:
    if definition.geometry_builder is None or definition.composer is None:
        raise ValueError(f"Template {definition.template_id} is not fully configured")

    composer_bank = dict(bank)
    composer_bank["density_level"] = {"sparse": 0, "normal": 1, "dense": 2}[variant.density_preset]
    blocks_by_region = definition.composer(rng, variant, composer_bank, definition)
    fingerprint_block = blocks_by_region.pop("_fingerprint")[0]
    fingerprint_metadata = dict(fingerprint_block.metadata)
    fingerprint_metadata.update(
        {
            "page_size": variant.page_size,
            "margin_preset": variant.margin_preset,
            "density_preset": variant.density_preset,
            "column_mode": variant.column_mode,
            "has_header": variant.has_header,
            "has_footer": variant.has_footer,
            "has_small_text": variant.has_small_text,
            "has_table_region": variant.has_table_region,
            "font_family": variant.font_family,
        }
    )
    regions = definition.geometry_builder(variant, page_size)
    region_plans: list[RegionPlan] = []
    title = definition.display_name
    for name, spec in regions.items():
        blocks = blocks_by_region.get(name, [])
        for block in blocks:
            if block.kind == "title" and block.text:
                title = block.text
                break
        region_plans.append(RegionPlan(spec=spec, blocks=blocks))
    return DocumentPlan(
        template_id=definition.template_id,
        source_type=definition.source_type,
        template_family=definition.template_family,
        title=title,
        regions=region_plans,
        content_fingerprint=make_content_fingerprint(fingerprint_metadata),
    )
