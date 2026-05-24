import { RouterProvider } from "react-router-dom";
import { router } from "@/router";
import { AuthBootstrap } from "@/components/auth/AuthBootstrap";
import { ToastContainer } from "@/components/ui/Toast";

export default function App() {
  return (
    <>
      <AuthBootstrap>
        <RouterProvider router={router} />
      </AuthBootstrap>
      {/* Global toast notifications -- rendered outside the router so they survive page transitions */}
      <ToastContainer />
    </>
  );
}
