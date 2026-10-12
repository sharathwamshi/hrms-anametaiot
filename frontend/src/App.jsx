import { Routes, Route } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import Loader from "./components/Loader";

import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Attendance from "./pages/Attendance";
import Leave from "./pages/Leave";
import Employees from "./pages/Employees";
import Payroll from "./pages/Payroll";
import Recruitment from "./pages/Recruitment";
import AllCandidates from "./pages/AllCandidates";
import AllPlacements from "./pages/AllPlacements";
import Recruiters from "./pages/Recruiters";
import Vendors from "./pages/Vendors";
import MockTestTake from "./pages/MockTestTake";
import Announcements from "./pages/Announcements";
import Assets from "./pages/Assets";
import Documents from "./pages/Documents";
import Profile from "./pages/Profile";

import { ROLES } from "./config/roles";

export default function App() {
  const { loading } = useAuth();
  if (loading) return <Loader label="Loading AnametaIOT HRMS..." />;

  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />

      <Route
        path="/attendance"
        element={
          <ProtectedRoute allow={[ROLES.MANAGER, ROLES.HR_OPERATIONS, ROLES.FINANCE_ACCOUNTS, ROLES.OPERATIONS, ROLES.HR_RECRUITER, ROLES.EMPLOYEE]}>
            <Attendance />
          </ProtectedRoute>
        }
      />

      <Route
        path="/leave"
        element={
          <ProtectedRoute>
            <Leave />
          </ProtectedRoute>
        }
      />

      <Route
        path="/employees"
        element={
          <ProtectedRoute allow={[ROLES.HR_OPERATIONS, ROLES.MANAGER, ROLES.OPERATIONS]}>
            <Employees />
          </ProtectedRoute>
        }
      />

      <Route
        path="/payroll"
        element={
          <ProtectedRoute>
            <Payroll />
          </ProtectedRoute>
        }
      />

      <Route
        path="/recruitment"
        element={
          <ProtectedRoute allow={[ROLES.HR_RECRUITER, ROLES.HR_OPERATIONS, ROLES.MANAGER]}>
            <Recruitment />
          </ProtectedRoute>
        }
      />

      <Route
        path="/all-candidates"
        element={
          <ProtectedRoute allow={[ROLES.HR_RECRUITER, ROLES.HR_OPERATIONS, ROLES.MANAGER, ROLES.FINANCE_ACCOUNTS]}>
            <AllCandidates />
          </ProtectedRoute>
        }
      />

      <Route
        path="/recruiters"
        element={
          <ProtectedRoute allow={[ROLES.FINANCE_ACCOUNTS, ROLES.HR_OPERATIONS, ROLES.MANAGER]}>
            <Recruiters />
          </ProtectedRoute>
        }
      />

      <Route
        path="/vendors"
        element={
          <ProtectedRoute allow={[ROLES.FINANCE_ACCOUNTS, ROLES.HR_OPERATIONS, ROLES.MANAGER]}>
            <Vendors />
          </ProtectedRoute>
        }
      />

      <Route
        path="/all-placements"
        element={
          <ProtectedRoute allow={[ROLES.FINANCE_ACCOUNTS, ROLES.HR_OPERATIONS, ROLES.MANAGER]}>
            <AllPlacements />
          </ProtectedRoute>
        }
      />

      <Route path="/test/:token" element={<MockTestTake />} />

      <Route
        path="/announcements"
        element={
          <ProtectedRoute>
            <Announcements />
          </ProtectedRoute>
        }
      />

      <Route
        path="/assets"
        element={
          <ProtectedRoute allow={[ROLES.HR_OPERATIONS, ROLES.OPERATIONS]}>
            <Assets />
          </ProtectedRoute>
        }
      />

      <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
      <Route path="/documents" element={<ProtectedRoute><Documents /></ProtectedRoute>} />
    </Routes>
  );
}
