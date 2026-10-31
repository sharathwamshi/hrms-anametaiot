const ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"];
const TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"];

function underThousand(value) {
  const hundreds = Math.floor(value / 100);
  const remainder = value % 100;
  const parts = [];
  if (hundreds) parts.push(`${ONES[hundreds]} Hundred`);
  if (remainder < 20 && remainder) parts.push(ONES[remainder]);
  if (remainder >= 20) parts.push(`${TENS[Math.floor(remainder / 10)]}${remainder % 10 ? ` ${ONES[remainder % 10]}` : ""}`);
  return parts.join(" ");
}

export function numberToWordsInr(value) {
  const numeric = Number(value || 0);
  let rupees = Math.floor(numeric);
  let paise = Math.round((numeric - rupees) * 100);
  if (paise === 100) {
    rupees += 1;
    paise = 0;
  }
  const parts = [];
  for (const [divisor, label] of [[10000000, "Crore"], [100000, "Lakh"], [1000, "Thousand"]]) {
    const count = Math.floor(rupees / divisor);
    if (count) {
      parts.push(`${underThousand(count)} ${label}`);
      rupees %= divisor;
    }
  }
  if (rupees) parts.push(underThousand(rupees));
  const result = `${parts.join(" ") || "Zero"} Rupees`;
  const paiseWords = paise ? ` and ${underThousand(paise)} Paise` : "";
  return `${result}${paiseWords} Only`;
}
