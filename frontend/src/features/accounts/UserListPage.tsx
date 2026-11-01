/**
 * User management page -- RDCO only.
 * Lists all users with role, active status, and quick actions:
 *   - Lock / unlock account
 *   - Change role (via modal)
 *   - Make or remove an office coordinator (IR-478, ADR-032 §4)
 * TODO: add "Create user" button.
 * TODO: add bulk import from CSV.
 */
import { useEffect, useId, useState } from "react";
import { accountsApi }  from "@/api/accounts";
import { PageHeader }   from "@/components/layout/PageHeader";
import { DataTable }    from "@/components/shared/DataTable";
import { EmptyState }   from "@/components/shared/EmptyState";
import { RoleBadge }    from "@/components/shared/RoleBadge";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Input }        from "@/components/ui/Input";
import { Button }       from "@/components/ui/Button";
import { Badge }        from "@/components/ui/Badge";
import { Modal }        from "@/components/ui/Modal";
import { ALL_ROLES, STAFF_ROLES } from "@/lib/constants";
import { useUIStore }   from "@/store/ui.store";
import type { ColumnDef } from "@tanstack/react-table";
import type { UserListItem } from "@/types/auth";
import { SearchGlyph } from "@/components/brand/IrisBrand";

/** The four office roles: the only ones the server lets coordinate. */
function isOfficeMember(user: UserListItem): boolean {
  return (STAFF_ROLES as readonly string[]).includes(user.role_name);
}

export default function UserListPage() {
  const addToast = useUIStore((s) => s.addToast);
  const roleSelectId = useId();

  const [users, setUsers]     = useState<UserListItem[]>([]);
  const [total, setTotal]     = useState(0);
  const [page, setPage]       = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [search, setSearch]   = useState("");

  // Lock/unlock confirm dialog
  const [lockTarget, setLockTarget] = useState<UserListItem | null>(null);
  // Role change modal
  const [roleTarget, setRoleTarget] = useState<UserListItem | null>(null);
  const [newRole, setNewRole]       = useState("");
  // Coordinator grant/removal confirm. Not an in-place toggle: an authority
  // grant must not be one misclick away.
  const [coordTarget, setCoordTarget]         = useState<UserListItem | null>(null);
  const [coordConfirming, setCoordConfirming] = useState(false);
  const [coordError, setCoordError]           = useState<string | null>(null);

  const load = (p = page) => {
    setLoading(true);
    accountsApi
      .userList({ page: p, search })
      .then(({ data }) => {
        setUsers(data.results);
        setTotal(data.count);
        setLoadFailed(false);
      })
      // An empty table after an error would read as "no users" (IR-745).
      .catch(() => setLoadFailed(true))
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

  const openCoordinator = (target: UserListItem) => {
    setCoordError(null);
    setCoordTarget(target);
  };

  const closeCoordinator = () => {
    setCoordTarget(null);
    setCoordError(null);
  };

  // The row changes only from the server's answer, so a refusal leaves it as
  // it was and keeps the dialog open with the reason.
  const handleCoordinator = async () => {
    if (!coordTarget) return;
    const granting = !coordTarget.is_office_coordinator;
    setCoordConfirming(true);
    setCoordError(null);
    try {
      const { data } = await accountsApi.setCoordinator(coordTarget.id, granting);
      setUsers((rows) => rows.map((row) =>
        row.id === data.id ? { ...row, is_office_coordinator: data.is_office_coordinator } : row,
      ));
      addToast({
        type: "success",
        message: `${coordTarget.email} ${granting ? "is now a coordinator" : "is no longer a coordinator"}.`,
      });
      setCoordTarget(null);
    } catch (err) {
      setCoordError(
        (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          ?? "The change could not be saved. Try again.",
      );
    } finally {
      setCoordConfirming(false);
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
      cell: ({ row }) => (
        <div className="flex flex-wrap items-center gap-1.5">
          <RoleBadge role={row.original.role_name} />
          {isOfficeMember(row.original) && row.original.is_office_coordinator && (
            <Badge>Coordinator</Badge>
          )}
        </div>
      ),
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
          {isOfficeMember(row.original) && (
            <Button variant="ghost" size="sm" onClick={() => openCoordinator(row.original)}>
              {row.original.is_office_coordinator ? "Remove coordinator" : "Make coordinator"}
            </Button>
          )}
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

  const coordAction = coordTarget?.is_office_coordinator ? "Remove coordinator" : "Make coordinator";

  return (
    <div>
      <PageHeader title="Users" description="Manage user accounts, roles and office coordinators." />

      <div className="flex gap-3 mb-4">
        <Input
          aria-label="Search users"
          placeholder="Search email or name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          leading={<SearchGlyph className="h-3.5 w-3.5" />}
          className="max-w-xs"
        />
        <Button variant="secondary" size="sm" onClick={handleSearch}>Filter</Button>
      </div>

      {loadFailed && !loading ? (
        <EmptyState
          framed
          tone="error"
          icon="fa-circle-exclamation"
          title="Couldn't load users"
          message="Check your connection and try again."
          action={<Button variant="outline" size="sm" onClick={() => load(page)}>Try again</Button>}
        />
      ) : (
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
      )}

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

      {/* Coordinator grant/removal confirm (ADR-032 §4) */}
      <ConfirmDialog
        open={!!coordTarget}
        title={`${coordAction}?`}
        message={
          coordTarget?.is_office_coordinator
            ? `${coordTarget.email} will no longer assign reviewers in ${coordTarget.role_name}; their existing assignments stay.`
            : `${coordTarget?.email} can assign, reassign and withdraw reviewers in ${coordTarget?.role_name}.`
        }
        confirmLabel={coordAction}
        confirming={coordConfirming}
        error={coordError}
        onConfirm={handleCoordinator}
        onCancel={closeCoordinator}
      />

      {/* Role change modal */}
      <Modal
        open={!!roleTarget}
        onClose={() => { setRoleTarget(null); setNewRole(""); }}
        title="Change Role"
      >
        <div className="flex flex-col gap-4">
          <p className="text-[14px] text-gray-600">
            Changing role for <strong>{roleTarget?.email}</strong>.
          </p>
          {/* `User.assign_role` drops the grant on every role change, even to
              the same role, because it was for the office the old role staffed. */}
          {roleTarget?.is_office_coordinator && (
            <p className="text-[14px] text-stone-700 border-l-2 border-brand pl-3">
              {roleTarget.email} coordinates {roleTarget.role_name}. Saving a role
              removes their coordinator status, even if you keep {roleTarget.role_name}.
            </p>
          )}
          <div>
            <label htmlFor={roleSelectId} className="text-[14px] font-medium text-gray-700 block mb-1">New role</label>
            <select
              id={roleSelectId}
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-[14px] outline-none
                focus:border-[#6B0F12] focus:ring-1 focus:ring-[#6B0F12]"
            >
              {ALL_ROLES.map((r) => (
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
