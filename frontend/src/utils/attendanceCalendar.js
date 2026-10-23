export function hasAutomaticClockoutBell(calendarData, date) {
  return (calendarData?.automatic_clockout_bell_dates || []).includes(date);
}
