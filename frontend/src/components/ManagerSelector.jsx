import { useId, useMemo, useState } from "react";

function initials(name = "") {
  return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0] || "").join("").toUpperCase();
}

export default function ManagerSelector({ managers, value, onChange, disabled = false }) {
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const optionsId = useId();
  const selectedManager = managers.find((manager) => String(manager.id) === String(value)) || null;
  const filteredManagers = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return managers.filter((manager) => manager.full_name.toLocaleLowerCase().includes(query));
  }, [managers, search]);

  const selectManager = (manager) => {
    onChange(String(manager.id));
    setSearch("");
    setOpen(false);
  };

  return (
    <div className="manager-selector">
      <div className="manager-selector-input-wrap">
        <input
          type="text"
          role="combobox"
          aria-label="Manager"
          aria-autocomplete="list"
          aria-expanded={open && !disabled}
          aria-controls={optionsId}
          autoComplete="off"
          placeholder="Search managers by name..."
          value={open ? search : selectedManager?.full_name || ""}
          disabled={disabled}
          onFocus={() => {
            if (!disabled) {
              setSearch("");
              setOpen(true);
            }
          }}
          onBlur={() => setOpen(false)}
          onChange={(event) => {
            setSearch(event.target.value);
            onChange("");
            setOpen(true);
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") setOpen(false);
            if (event.key === "Enter" && open && filteredManagers[0]) {
              event.preventDefault();
              selectManager(filteredManagers[0]);
            }
          }}
        />
        {selectedManager && !disabled && (
          <button
            type="button"
            className="manager-selector-clear"
            aria-label="Clear manager"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              onChange("");
              setSearch("");
              setOpen(true);
            }}
          >
            ×
          </button>
        )}
        {open && !disabled && (
          <div className="manager-selector-options" id={optionsId} role="listbox" aria-label="Available managers">
            {filteredManagers.length > 0 ? filteredManagers.map((manager) => (
              <button
                type="button"
                role="option"
                aria-selected={String(manager.id) === String(value)}
                className="manager-selector-option"
                key={manager.id}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => selectManager(manager)}
              >
                {manager.full_name}
              </button>
            )) : <div className="manager-selector-empty">No managers found.</div>}
          </div>
        )}
      </div>
      {selectedManager && (
        <div className="manager-details-card">
          <div className="manager-avatar" aria-hidden="true">{initials(selectedManager.full_name)}</div>
          <div className="manager-details">
            <strong>{selectedManager.full_name}</strong>
            <span>{selectedManager.designation || "Designation not specified"}</span>
            <span>{selectedManager.email}</span>
            <span>{selectedManager.department || "Department not specified"}</span>
          </div>
        </div>
      )}
    </div>
  );
}
