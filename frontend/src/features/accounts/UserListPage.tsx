/**
 * User management page -- staff/admin only.
 * Lists all users with role, active status, and quick actions:
 *   - Lock / unlock account
 *   - Change role (via modal)
 * TODO: add "Create user" button.
 * TODO: add bulk import from CSV.
 */
import { useEffect, useState } from "react";
import { accountsApi }  from "@/api/accounts";
import { PageHeader }   from "@/components/layout/PageHeader";
import { DataTable }    from "@/components/shared/DataTable";
import { RoleBadge }    from "@/components/shared/RoleBadge";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Input }        from "@/components/ui/Input";
import { Button }       from "@/components/ui/Button";
import { Badge }        from "@/components/ui/Badge";
import { Modal }        from "@/components/ui/Modal";
import { useUIStore }   from "@/store/ui.store";
import type { ColumnDef } from "@tanstack/react-table";
import type { UserListItem } from "@/types/auth";

export default function UserListPage() {
  const addToast = useUIStore((s) => s.addToast);

  const [users, setUsers]     = useState<UserListItem[]>([]);
  const [total, setTotal]     = useState(0);
  const [page, setPage]       = useState(1);
  const [loading, setLoading] = useState(true);
  const [search, setSearch]   = useState("");

  // Lock/unlock confirm dialog
  const [lockTarget, setLockTarget] = useState<UserListItem | null>(null);
  // Role change modal
  const [roleTarget, setRoleTarget] = useState<UserListItem | null>(null);
  const [newRole, setNewRole]       = useState("");

  const load = (p = page) => {
    setLoading(true);
    accountsApi
      .userList({ page: p, search })
      .then(({ data }) => {
        setUsers(data.results);
        setTotal(data.count);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(page); }, [page]);

  const handleSearch = () => { setPage(1); load(1); };

  const handleToggleLock = async () => {
    if (!lockTarget) return;
    try {
      await accountsApi.setLocked(lockTarget.id, !lockTarget.is_locked);
      addToast({ type: "success", message: `User ${lockTarget.is_locked ? "unlocked" : "locked"}.` });
      load(page);
    } catch {
      addToast({ type: "error", message: "Action failed." });
    } finally {
      setLockTarget(null);
    }
  };

  const handleRoleChange = async () => {
    if (!roleTarget || !newRole) return;
    try {
      await accountsApi.setRole(roleTarget.id, newRole);
      addToast({ type: "success", message: "Role updated." });
      load(page);
    } catch {
      addToast({ type: "error", message: "Role change failed." });
    } finally {
      setRoleTarget(null);
      setNewRole("");
    }
  };

  const columns: ColumnDef<UserListItem, unknown>[] = [
    {
      header: "Email",
      accessorKey: "email",
      cell: ({ getValue }) => (
        <span className="font-medium text-gray-900">{getValue<string>()}</span>
      ),
    },
    {
      header: "Name",
      id: "name",
      cell: ({ row }) => (
        <span className="text-gray-700">
          {row.original.first_name} {row.original.last_name}
        </span>
      ),
    },
    {
      header: "Role",
      accessorKey: "role_name",
      cell: ({ getValue }) => <RoleBadge role={getValue<string>()} />,
    },
    {
      header: "Status",
      accessorKey: "is_active",
      cell: ({ row }) => (
        <Badge variant={row.original.is_locked ? "danger" : row.original.is_active ? "success" : "neutral"}>
          {row.original.is_locked ? "Locked" : row.original.is_active ? "Active" : "Inactive"}
        </Badge>
      ),
    },
    {
      header: "",
      id: "actions",
      cell: ({ row }) => (
        <div className="flex gap-2 justify-end">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => { setRoleTarget(row.original); setNewRole(row.original.role_name); }}
          >
            Change role
          </Button>
          <Button
            variant={row.original.is_locked ? "secondary" : "danger"}
            size="sm"
            onClick={() => setLockTarget(row.original)}
          >
            {row.original.is_locked ? "Unlock" : "Lock"}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title="Users" description="Manage user accounts and roles." />

      <div className="flex gap-3 mb-4">
        <Input
          placeholder="Search email or name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          leading={<i className="fa fa-search text-[13px]" aria-hidden />}
          className="max-w-xs"
        />
        <Button variant="secondary" size="sm" onClick={handleSearch}>Filter</Button>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <DataTable
          data={users}
          columns={columns}
          loading={loading}
          page={page}
          pageSize={20}
          totalCount={total}
          onPageChange={setPage}
        />
      </div>

      {/* Lock/unlock confirm */}
      <ConfirmDialog
        open={!!lockTarget}
        title={lockTarget?.is_locked ? "Unlock account?" : "Lock account?"}
        message={
          lockTarget?.is_locked
            ? `${lockTarget.email} will be able to log in again.`
            : `${lockTarget?.email} will be prevented from logging in.`
        }
        confirmLabel={lockTarget?.is_locked ? "Unlock" : "Lock"}
        danger={!lockTarget?.is_locked}
        onConfirm={handleToggleLock}
        onCancel={() => setLockTarget(null)}
      />

      {/* Role change modal */}
      <Modal
        open={!!roleTarget}
        onClose={() => { setRoleTarget(null); setNewRole(""); }}
        title="Change Role"
      >
        <div className="flex flex-col gap-4">
          <p className="text-[13px] text-gray-600">
            Changing role for <strong>{roleTarget?.email}</strong>.
          </p>
          <div>
            <label className="text-[13px] font-medium text-gray-700 block mb-1">New Role</label>
            <select
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-[13px] outline-none
                focus:border-[#6B0F12] focus:ring-1 focus:ring-[#6B0F12]"
            >
              {["Student","Adviser","KTTO","RDCO","ITSO","IERC"].map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setRoleTarget(null)}>Cancel</Button>
            <Button onClick={handleRoleChange}>Save</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
