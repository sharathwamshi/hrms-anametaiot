import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Loader from "./Loader";

export default function ProtectedRoute({ children, allow }) {
  const { user, loading } = useAuth();

  if (loading) return <Loader label="Checking your session..." />;
  if (!user) return <Navigate to="/login" replace />;
  if (allow && !allow.includes(user.role)) {
    return (
      <div className="loader-wrap">
        You do not have access to this page for your role ({user.role}).
      </div>
    );
  }
  return children;
}
