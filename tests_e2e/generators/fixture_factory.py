"""
Fixture Factory: Programmatically generates all 15 authoritative reference statement fixtures
and paired ground-truth JSON files in tests_e2e/fixtures/.
"""
import os
import json
from decimal import Decimal
from typing import Dict, Any, List

from tests_e2e.generators.statement_generator import (
    SyntheticStatementGenerator,
    StatementDataSpec,
)


def generate_all_fixtures(fixtures_dir: str) -> Dict[str, Dict[str, Any]]:
    """Generates all 15 test ground truth fixtures into fixtures_dir."""
    stmts_dir = os.path.join(fixtures_dir, "statements")
    gt_dir = os.path.join(fixtures_dir, "ground_truth")
    os.makedirs(stmts_dir, exist_ok=True)
    os.makedirs(gt_dir, exist_ok=True)

    catalog = {}

    # 1. TC-01: Chase Single-Page Checking (Digital PDF)
    spec_01 = StatementDataSpec(
        bank_name="JPMorgan Chase Bank, N.A.",
        account_number="************4921",
        period_start="2026-08-01",
        period_end="2026-08-31",
        starting_balance=Decimal("3450.00"),
        raw_transactions=[
            {"date": "2026-08-02", "payee": "Direct Deposit ACME Corp", "type": "credit", "amount": "2800.00", "category": "Income / Payroll"},
            {"date": "2026-08-05", "payee": "Trader Joe's Groceries", "type": "debit", "amount": "142.15", "category": "Groceries"},
            {"date": "2026-08-07", "payee": "Starbucks Coffee #1042", "type": "debit", "amount": "6.75", "category": "Dining & Food"},
            {"date": "2026-08-12", "payee": "Con Edison Electric Utility", "type": "debit", "amount": "94.30", "category": "Utilities"},
            {"date": "2026-08-18", "payee": "Amazon Prime Subscription", "type": "debit", "amount": "14.99", "category": "Software & Subscriptions"},
            {"date": "2026-08-25", "payee": "Zelle Transfer from Dave", "type": "credit", "amount": "150.00", "category": "Transfers & Wire"},
        ],
        layout_style="standard_table",
    )
    catalog["tc01"] = SyntheticStatementGenerator.generate(
        spec_01,
        os.path.join(stmts_dir, "tc01_chase_single_page.pdf"),
        os.path.join(gt_dir, "tc01_chase_single_page.json"),
        format_type="digital_pdf",
    )

    # 2. TC-02: Bank of America Multi-Page Checking (Digital PDF)
    boa_txs = []
    base_dates = [f"2026-07-{d:02d}" for d in range(1, 29)]
    for i, d in enumerate(base_dates):
        if i % 5 == 0:
            boa_txs.append({"date": d, "payee": f"Client Wire Payment #{i+100}", "type": "credit", "amount": "1250.00", "category": "Income / Payroll"})
        else:
            boa_txs.append({"date": d, "payee": f"Office Depot & Supplies #{i+10}", "type": "debit", "amount": f"{45.50 + i * 2.10:.2f}", "category": "Shopping & Retail"})
    spec_02 = StatementDataSpec(
        bank_name="Bank of America, N.A.",
        account_number="************7119",
        period_start="2026-07-01",
        period_end="2026-07-31",
        starting_balance=Decimal("12500.00"),
        raw_transactions=boa_txs,
        layout_style="standard_table",
    )
    catalog["tc02"] = SyntheticStatementGenerator.generate(
        spec_02,
        os.path.join(stmts_dir, "tc02_boa_multi_page.pdf"),
        os.path.join(gt_dir, "tc02_boa_multi_page.json"),
        format_type="digital_pdf",
    )

    # 3. TC-03: Wells Fargo Two-Column (Digital PDF)
    spec_03 = StatementDataSpec(
        bank_name="Wells Fargo Bank, N.A.",
        account_number="************3302",
        period_start="2026-09-01",
        period_end="2026-09-30",
        starting_balance=Decimal("5600.25"),
        raw_transactions=[
            {"date": "2026-09-03", "payee": "Payroll Deposit BioTech Inc", "type": "credit", "amount": "3450.00", "category": "Income / Payroll"},
            {"date": "2026-09-06", "payee": "Target Superstore Store 082", "type": "debit", "amount": "88.40", "category": "Shopping & Retail"},
            {"date": "2026-09-10", "payee": "Chevron Gas Station 4421", "type": "debit", "amount": "52.10", "category": "Travel & Transportation"},
            {"date": "2026-09-14", "payee": "Federal Tax Refund IRS", "type": "credit", "amount": "920.00", "category": "Taxes"},
            {"date": "2026-09-22", "payee": "Kaiser Permanente Copay", "type": "debit", "amount": "35.00", "category": "Healthcare & Medical"},
        ],
        layout_style="two_column",
    )
    catalog["tc03"] = SyntheticStatementGenerator.generate(
        spec_03,
        os.path.join(stmts_dir, "tc03_wells_fargo_two_column.pdf"),
        os.path.join(gt_dir, "tc03_wells_fargo_two_column.json"),
        format_type="digital_pdf",
    )

    # 4. TC-04: Single-Column Signed (Digital PDF)
    spec_04 = StatementDataSpec(
        bank_name="Capital One 360 Checking",
        account_number="************9914",
        period_start="2026-06-01",
        period_end="2026-06-30",
        starting_balance=Decimal("1890.50"),
        raw_transactions=[
            {"date": "2026-06-02", "payee": "Interest Paid", "type": "credit", "amount": "12.45", "category": "Income / Payroll"},
            {"date": "2026-06-11", "payee": "Uber Technologies Ride", "type": "debit", "amount": "27.80", "category": "Travel & Transportation"},
            {"date": "2026-06-19", "payee": "Whole Foods Market", "type": "debit", "amount": "114.90", "category": "Groceries"},
        ],
        layout_style="signed_single",
    )
    catalog["tc04"] = SyntheticStatementGenerator.generate(
        spec_04,
        os.path.join(stmts_dir, "tc04_single_column_signed.pdf"),
        os.path.join(gt_dir, "tc04_single_column_signed.json"),
        format_type="digital_pdf",
    )

    # 5. TC-05: Credit Union Statement (Digital PDF)
    spec_05 = StatementDataSpec(
        bank_name="Navy Federal Credit Union",
        account_number="************6631",
        period_start="2026-05-01",
        period_end="2026-05-31",
        starting_balance=Decimal("4120.00"),
        raw_transactions=[
            {"date": "2026-05-04", "payee": "US Treasury Military Pay", "type": "credit", "amount": "3800.00", "category": "Income / Payroll"},
            {"date": "2026-05-08", "payee": "Mortgage Payment NFCU", "type": "debit", "amount": "1650.00", "category": "Rent & Mortgage"},
            {"date": "2026-05-18", "payee": "Geico Auto Insurance", "type": "debit", "amount": "145.20", "category": "Insurance"},
        ],
        layout_style="standard_table",
    )
    catalog["tc05"] = SyntheticStatementGenerator.generate(
        spec_05,
        os.path.join(stmts_dir, "tc05_credit_union_parentheses.pdf"),
        os.path.join(gt_dir, "tc05_credit_union_parentheses.json"),
        format_type="digital_pdf",
    )

    # 6. TC-06: Scanned Statement Clean (PNG Image)
    spec_06 = StatementDataSpec(
        bank_name="Citibank Personal Banking",
        account_number="************5510",
        period_start="2026-04-01",
        period_end="2026-04-30",
        starting_balance=Decimal("2200.00"),
        raw_transactions=[
            {"date": "2026-04-05", "payee": "Direct Deposit Salary", "type": "credit", "amount": "2100.00", "category": "Income / Payroll"},
            {"date": "2026-04-12", "payee": "Chipotle Mexican Grill", "type": "debit", "amount": "18.50", "category": "Dining & Food"},
            {"date": "2026-04-20", "payee": "Netflix Subscription", "type": "debit", "amount": "19.99", "category": "Software & Subscriptions"},
        ],
        layout_style="standard_table",
    )
    catalog["tc06"] = SyntheticStatementGenerator.generate(
        spec_06,
        os.path.join(stmts_dir, "tc06_scanned_clean.png"),
        os.path.join(gt_dir, "tc06_scanned_clean.json"),
        format_type="png",
    )

    # 7. TC-07: Scanned Degraded & Skewed (JPEG Image)
    spec_07 = StatementDataSpec(
        bank_name="Barclays Bank UK",
        account_number="************8821",
        period_start="2026-03-01",
        period_end="2026-03-31",
        starting_balance=Decimal("1500.00"),
        raw_transactions=[
            {"date": "2026-03-02", "payee": "BACS Transfer Salary", "type": "credit", "amount": "1950.00", "category": "Income / Payroll"},
            {"date": "2026-03-10", "payee": "Sainsbury's Supermarket", "type": "debit", "amount": "76.40", "category": "Groceries"},
        ],
        layout_style="standard_table",
    )
    catalog["tc07"] = SyntheticStatementGenerator.generate(
        spec_07,
        os.path.join(stmts_dir, "tc07_scanned_skewed_noisy.jpg"),
        os.path.join(gt_dir, "tc07_scanned_skewed_noisy.json"),
        format_type="jpeg",
        skew_angle=2.5,
        add_noise=True,
    )

    # 8. TC-08: European International Statement (Digital PDF)
    spec_08 = StatementDataSpec(
        bank_name="BNP Paribas France",
        account_number="FR7630006000011234567890189",
        period_start="2026-02-01",
        period_end="2026-02-28",
        starting_balance=Decimal("4500.00"),
        raw_transactions=[
            {"date": "2026-02-05", "payee": "Virement Salaire Mensuel", "type": "credit", "amount": "3200.00", "category": "Income / Payroll"},
            {"date": "2026-02-14", "payee": "Carrefour Supermarche", "type": "debit", "amount": "125.60", "category": "Groceries"},
            {"date": "2026-02-20", "payee": "SNCF Billet de Train", "type": "debit", "amount": "89.00", "category": "Travel & Transportation"},
        ],
        currency="EUR",
        layout_style="standard_table",
    )
    catalog["tc08"] = SyntheticStatementGenerator.generate(
        spec_08,
        os.path.join(stmts_dir, "tc08_european_intl.pdf"),
        os.path.join(gt_dir, "tc08_european_intl.json"),
        format_type="digital_pdf",
    )

    # 9. TC-09: Deliberate Missing Row Anomaly (Digital PDF)
    spec_09 = StatementDataSpec(
        bank_name="TD Bank Commercial",
        account_number="************4419",
        period_start="2026-01-01",
        period_end="2026-01-31",
        starting_balance=Decimal("3000.00"),
        raw_transactions=[
            {"date": "2026-01-05", "payee": "Deposit Vendor Payment", "type": "credit", "amount": "1500.00", "category": "Income / Payroll"},
            {"date": "2026-01-10", "payee": "Omitted Payment Vendor", "type": "debit", "amount": "150.25", "category": "Shopping & Retail"},
            {"date": "2026-01-18", "payee": "Office Depot Supplies", "type": "debit", "amount": "80.00", "category": "Shopping & Retail"},
        ],
        layout_style="standard_table",
        inject_anomaly="missing_row",
        anomaly_row_idx=1,
    )
    catalog["tc09"] = SyntheticStatementGenerator.generate(
        spec_09,
        os.path.join(stmts_dir, "tc09_anomaly_missing_row.pdf"),
        os.path.join(gt_dir, "tc09_anomaly_missing_row.json"),
        format_type="digital_pdf",
    )

    # 10. TC-10: Deliberate Sign Inversion Anomaly (Digital PDF)
    spec_10 = StatementDataSpec(
        bank_name="PNC Bank Business",
        account_number="************1190",
        period_start="2026-09-01",
        period_end="2026-09-30",
        starting_balance=Decimal("8000.00"),
        raw_transactions=[
            {"date": "2026-09-02", "payee": "Client Consulting Fee", "type": "credit", "amount": "2500.00", "category": "Income / Payroll"},
            {"date": "2026-09-08", "payee": "Cloud Hosting Server AWS", "type": "debit", "amount": "100.00", "category": "Software & Subscriptions"},
            {"date": "2026-09-15", "payee": "Staples Business Stationery", "type": "debit", "amount": "45.00", "category": "Shopping & Retail"},
        ],
        layout_style="standard_table",
        inject_anomaly="sign_inversion",
        anomaly_row_idx=1,
    )
    catalog["tc10"] = SyntheticStatementGenerator.generate(
        spec_10,
        os.path.join(stmts_dir, "tc10_anomaly_sign_inversion.pdf"),
        os.path.join(gt_dir, "tc10_anomaly_sign_inversion.json"),
        format_type="digital_pdf",
    )

    # 11. TC-11: Deliberate Out-of-Order Dates (Digital PDF)
    spec_11 = StatementDataSpec(
        bank_name="U.S. Bank Retail",
        account_number="************6720",
        period_start="2026-08-01",
        period_end="2026-08-31",
        starting_balance=Decimal("2500.00"),
        raw_transactions=[
            {"date": "2026-08-02", "payee": "Deposit ATM Cash", "type": "credit", "amount": "400.00", "category": "Income / Payroll"},
            {"date": "2026-08-15", "payee": "Mid-Month Wire Transfer", "type": "credit", "amount": "800.00", "category": "Transfers & Wire"},
            {"date": "2026-08-08", "payee": "Retroactive Adjustment Fee", "type": "debit", "amount": "25.00", "category": "Bank Fees"},
        ],
        layout_style="standard_table",
        inject_anomaly="out_of_order",
        anomaly_row_idx=1,
    )
    catalog["tc11"] = SyntheticStatementGenerator.generate(
        spec_11,
        os.path.join(stmts_dir, "tc11_anomaly_out_of_order.pdf"),
        os.path.join(gt_dir, "tc11_anomaly_out_of_order.json"),
        format_type="digital_pdf",
    )

    # 12. TC-12: Overdraft / Negative Balance (Digital PDF)
    spec_12 = StatementDataSpec(
        bank_name="Fifth Third Bank",
        account_number="************8801",
        period_start="2026-07-01",
        period_end="2026-07-31",
        starting_balance=Decimal("50.00"),
        raw_transactions=[
            {"date": "2026-07-03", "payee": "Automated Utility Withdrawal", "type": "debit", "amount": "134.20", "category": "Utilities"},  # balance goes negative: -84.20
            {"date": "2026-07-04", "payee": "Overdraft Protection Fee", "type": "debit", "amount": "35.00", "category": "Bank Fees"},    # balance: -119.20
            {"date": "2026-07-08", "payee": "Deposit Recovery Funds", "type": "credit", "amount": "500.00", "category": "Income / Payroll"}, # balance recovers: +380.80
        ],
        layout_style="standard_table",
    )
    catalog["tc12"] = SyntheticStatementGenerator.generate(
        spec_12,
        os.path.join(stmts_dir, "tc12_negative_overdraft.pdf"),
        os.path.join(gt_dir, "tc12_negative_overdraft.json"),
        format_type="digital_pdf",
    )

    # 13. TC-13: Zero-Amount Transactions / Waivers (Digital PDF)
    spec_13 = StatementDataSpec(
        bank_name="Silicon Valley Commercial",
        account_number="************9090",
        period_start="2026-05-01",
        period_end="2026-05-31",
        starting_balance=Decimal("10000.00"),
        raw_transactions=[
            {"date": "2026-05-02", "payee": "Monthly Account Maintenance Fee", "type": "debit", "amount": "0.00", "category": "Bank Fees"},
            {"date": "2026-05-15", "payee": "Relationship Reward Credit", "type": "credit", "amount": "0.00", "category": "Bank Fees"},
            {"date": "2026-05-20", "payee": "Consulting Revenue", "type": "credit", "amount": "4500.00", "category": "Income / Payroll"},
        ],
        layout_style="standard_table",
    )
    catalog["tc13"] = SyntheticStatementGenerator.generate(
        spec_13,
        os.path.join(stmts_dir, "tc13_zero_amount_dividend.pdf"),
        os.path.join(gt_dir, "tc13_zero_amount_dividend.json"),
        format_type="digital_pdf",
    )

    # 14. TC-14: Extreme Large Values / Corporate Treasury (Digital PDF)
    spec_14 = StatementDataSpec(
        bank_name="Global Corporate Treasury Bank",
        account_number="************7777",
        period_start="2026-04-01",
        period_end="2026-04-30",
        starting_balance=Decimal("500000000.00"),
        raw_transactions=[
            {"date": "2026-04-05", "payee": "Syndicated Loan Liquidity Draw", "type": "credit", "amount": "250000000.00", "category": "Income / Payroll"},
            {"date": "2026-04-18", "payee": "Corporate Dividend Distribution", "type": "debit", "amount": "125000000.50", "category": "Miscellaneous"},
        ],
        layout_style="standard_table",
    )
    catalog["tc14"] = SyntheticStatementGenerator.generate(
        spec_14,
        os.path.join(stmts_dir, "tc14_extreme_large_values.pdf"),
        os.path.join(gt_dir, "tc14_extreme_large_values.json"),
        format_type="digital_pdf",
    )

    # 15. TC-15: Leap Year Date Statement (Digital PDF)
    spec_15 = StatementDataSpec(
        bank_name="Federal Reserve Credit Union",
        account_number="************2929",
        period_start="2028-02-01",
        period_end="2028-02-29",
        starting_balance=Decimal("3500.00"),
        raw_transactions=[
            {"date": "2028-02-14", "payee": "Valentine Florist Purchase", "type": "debit", "amount": "85.00", "category": "Dining & Food"},
            {"date": "2028-02-29", "payee": "Leap Day Special Bonus Payroll", "type": "credit", "amount": "1000.00", "category": "Income / Payroll"},
        ],
        layout_style="standard_table",
    )
    catalog["tc15"] = SyntheticStatementGenerator.generate(
        spec_15,
        os.path.join(stmts_dir, "tc15_leap_year_feb29.pdf"),
        os.path.join(gt_dir, "tc15_leap_year_feb29.json"),
        format_type="digital_pdf",
    )

    # Write summary catalog.json
    with open(os.path.join(fixtures_dir, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump({k: v["metadata"] for k, v in catalog.items()}, f, indent=2)

    return catalog


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_fixtures = os.path.join(base_dir, "fixtures")
    print(f"Generating synthetic statement fixtures into: {target_fixtures}")
    res = generate_all_fixtures(target_fixtures)
    print(f"Successfully generated {len(res)} statement fixtures with ground truth JSONs.")
