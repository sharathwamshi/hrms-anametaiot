const OPTIONS = [
  { value: "full_day", label: "Full Day", quantity: "1 day" },
  { value: "first_half", label: "First Half", quantity: "0.5 day" },
  { value: "second_half", label: "Second Half", quantity: "0.5 day" },
];

export default function LeaveDurationSelector({ value, onChange }) {
  return (
    <fieldset className="leave-duration-field">
      <legend>Leave Duration</legend>
      <div className="leave-duration-options">
        {OPTIONS.map((option) => (
          <label className="leave-duration-option" key={option.value}>
            <input
              type="radio"
              name="leave-duration"
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
            />
            <span>
              <strong>{option.label}</strong>
              <small>{option.quantity}</small>
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
