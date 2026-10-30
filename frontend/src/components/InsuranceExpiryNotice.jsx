import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client from "../api/client";
import { ROLES } from "../config/roles";
import { useAuth } from "../context/AuthContext";

export default function InsuranceExpiryNotice() {
  const { user } = useAuth();
  const [policies, setPolicies] = useState([]);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (![ROLES.EMPLOYEE, ROLES.CONTRACT_EMPLOYEE].includes(user?.role)) return undefined;
    let active = true;
    client.get("/insurance", { params: { status: "expiring_soon" } })
      .then(({ data }) => {
        if (!active || !data.length) return;
        setPolicies(data);
        setVisible(true);
      })
      .catch(() => {
        // The insurance page displays API errors; the shared notice is best-effort.
      });
    return () => { active = false; };
  }, [user?.id, user?.role]);

  if (!visible || !policies.length) return null;

  const dismiss = () => {
    setVisible(false);
  };

  return (
    <aside className="insurance-expiry-notice" role="status" aria-label="Insurance expiry reminder">
      <button type="button" className="insurance-expiry-notice-close" onClick={dismiss} aria-label="Close insurance expiry reminder">×</button>
      <strong>Insurance expiry reminder</strong>
      <p>
        {policies.length === 1
          ? `${policies[0].provider_name} ${policies[0].insurance_type} insurance expires on ${policies[0].policy_expiry_date}.`
          : `${policies.length} insurance policies are expiring soon.`}
      </p>
      <Link to="/insurance" className="btn btn-sm btn-outline" onClick={dismiss}>View insurance</Link>
    </aside>
  );
}
