# Validation report

Overall: **all checks passed**

## Tie-outs (correct books vs source systems)

| Result | Check | Detail |
|---|---|---|
| PASS | Record IDs are unique in every source table | no duplicates |
| PASS | Trial balance nets to zero (expected) | 0.00 |
| PASS | Trial balance nets to zero (as-booked) | 0.00 |
| PASS | GL cash = bank statements at every month-end | max diff 0.00 |
| PASS | GL accounts receivable = open invoices in billing | max diff 0.00 |
| PASS | GL accounts payable = unpaid bills in AP system | max diff 0.00 |
| PASS | GL card liability = card activity less statement payments | max diff 0.00 |
| PASS | Stripe clearing = charges not yet paid out | max diff 0.00 |

## SaaS metrics (from billing events)

| Month | ARR | Customers | SMB / MM / Ent | Net new ARR | NRR (TTM) | GRR (TTM) |
|---|---:|---:|---|---:|---:|---:|
| Oct 2024 | $2.91M | 79 | 50 / 26 / 3 | $383k | 109% | 97% |
| Nov 2024 | $3.03M | 87 | 58 / 26 / 3 | $126k | 110% | 99% |
| Dec 2024 | $3.22M | 92 | 61 / 28 / 3 | $185k | 111% | 99% |
| Jan 2025 | $3.35M | 95 | 63 / 29 / 3 | $127k | 110% | 98% |
| Feb 2025 | $3.61M | 100 | 66 / 30 / 4 | $266k | 110% | 98% |
| Mar 2025 | $3.71M | 106 | 72 / 30 / 4 | $96k | 109% | 97% |
| Apr 2025 | $3.71M | 110 | 76 / 30 / 4 | $5k | 103% | 91% |
| May 2025 | $4.03M | 116 | 81 / 30 / 5 | $315k | 101% | 90% |
| Jun 2025 | $4.51M | 132 | 91 / 36 / 5 | $480k | 103% | 91% |
| Jul 2025 | $4.70M | 138 | 95 / 38 / 5 | $189k | 104% | 92% |
| Aug 2025 | $5.04M | 141 | 97 / 38 / 6 | $341k | 102% | 90% |
| Sep 2025 | $5.06M | 142 | 98 / 38 / 6 | $23k | 100% | 90% |
| Oct 2025 | $5.41M | 153 | 105 / 42 / 6 | $342k | 102% | 91% |
| Nov 2025 | $6.29M | 163 | 109 / 45 / 9 | $883k | 100% | 90% |
| Dec 2025 | $6.62M | 172 | 114 / 49 / 9 | $327k | 101% | 90% |
| Jan 2026 | $7.27M | 187 | 121 / 56 / 10 | $652k | 102% | 90% |
| Feb 2026 | $7.51M | 191 | 123 / 57 / 11 | $243k | 100% | 88% |
| Mar 2026 | $7.76M | 195 | 125 / 59 / 11 | $250k | 100% | 87% |
| Apr 2026 | $7.94M | 198 | 126 / 61 / 11 | $182k | 105% | 90% |
| May 2026 | $8.32M | 204 | 131 / 62 / 11 | $379k | 105% | 89% |
| Jun 2026 | $8.85M | 213 | 138 / 63 / 12 | $524k | 104% | 89% |
| Jul 2026 | $9.28M | 223 | 146 / 65 / 12 | $438k | 102% | 87% |
| Aug 2026 | $9.41M | 234 | 157 / 65 / 12 | $128k | 96% | 82% |
| Sep 2026 | $10.01M | 247 | 162 / 72 / 13 | $596k | 97% | 82% |
| Oct 2026 | $11.00M | 261 | 169 / 77 / 15 | $996k | 99% | 83% |
| PASS | ARR at Oct 2026 in the $8-12M range | $11.00M |
| PASS | YoY ARR growth between 50% and 110% | 104% |

## P&L by month (correct books, $000s)

| Month | Revenue | Gross margin | Opex | Net income | Op. cash burn |
|---|---:|---:|---:|---:|---:|
| Nov 2024 | 268 | 77% | 621 | -379 | 147 |
| Dec 2024 | 288 | 77% | 622 | -364 | 303 |
| Jan 2025 | 285 | 76% | 726 | -471 | 353 |
| Feb 2025 | 292 | 76% | 714 | -459 | 379 |
| Mar 2025 | 335 | 78% | 736 | -442 | 563 |
| Apr 2025 | 322 | 79% | 761 | -477 | 617 |
| May 2025 | 327 | 78% | 780 | -495 | 531 |
| Jun 2025 | 380 | 80% | 793 | -464 | 652 |
| Jul 2025 | 424 | 80% | 950 | -586 | -56 |
| Aug 2025 | 456 | 80% | 831 | -441 | 315 |
| Sep 2025 | 434 | 79% | 879 | -513 | -27 |
| Oct 2025 | 468 | 80% | 964 | -569 | 720 |
| Nov 2025 | 557 | 82% | 929 | -447 | 480 |
| Dec 2025 | 594 | 82% | 911 | -406 | -32 |
| Jan 2026 | 676 | 84% | 984 | -399 | -149 |
| Feb 2026 | 617 | 80% | 944 | -429 | 52 |
| Mar 2026 | 684 | 84% | 1,036 | -446 | 910 |
| Apr 2026 | 667 | 83% | 1,124 | -557 | 650 |
| May 2026 | 698 | 83% | 1,209 | -615 | 644 |
| Jun 2026 | 726 | 83% | 1,295 | -571 | 647 |
| Jul 2026 | 779 | 77% | 1,311 | -591 | 427 |
| Aug 2026 | 821 | 84% | 1,616 | -810 | 308 |
| Sep 2026 | 818 | 78% | 1,644 | -884 | 868 |
| Oct 2026 | 974 | 85% | 1,590 | -649 | 1,048 |
| PASS | Gross margin between 70% and 85% every month | range 76% to 85% |
| PASS | Cash never below $1M | low point $6.7M |
