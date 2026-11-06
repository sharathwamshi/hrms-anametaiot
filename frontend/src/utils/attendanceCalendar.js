export const AUTO_CLOCK_OUT_MESSAGE = "You forgot to clock out yesterday.";

export function hasAutomaticClockoutBell(calendarData, date) {
  return (calendarData?.automatic_clockout_bell_dates || []).includes(date);
}

export function toggleAutomaticClockoutNotification(currentDate, date) {
  return currentDate === date ? null : date;
}
