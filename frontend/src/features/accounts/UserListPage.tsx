/**
 * User management page -- RDCO and the System Admin (ADR-051 §4, amended).
 * Lists all users with role, active status, and the actions this viewer may
 * take on each row (`accountActions.ts`), together in one "⋯" menu per row
 * (IR-1077) and none at all on the viewer's own row:
 *   - Lock / unlock account (a confirm that names the person)
 *   - Change role (via modal)
 *   - Make or remove an office coordinator (IR-478, ADR-032 §4)
 * TODO: add "Create user" button.
 * TODO: add bulk import from CSV.
 */
import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { accountsApi }  from "@/api/accounts";
import { PageHeader }   from "@/components/layout/PageHeader";
import { DataTable }    from "@/components/shared/DataTable";
import { EmptyState }   from "@/components/shared/EmptyState";
import { RoleBadge }    from "@/components/shared/RoleBadge";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Input }        from "@/components/ui/Input";
import { Button }       from "@/components/ui/Button";
import { Select }       from "@/components/ui/Select";
import { Badge }        from "@/components/ui/Badge";
import { Modal }        from "@/components/ui/Modal";
import { STAFF_ROLES } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";
import { useUIStore }   from "@/store/ui.store";
import { rolesToOffer, rowActions } from "./accountActions";
import { RowMenu, type RowMenuItem } from "./RowMenu";
import type { ColumnDef } from "@tanstack/react-table";
import type { UserListItem } from "@/types/auth";
import { SearchGlyph } from "@/components/brand/IrisBrand";

/** What a person is called in a dialog: their name, or their email when they have none. */
function displayName(user: UserListItem): string {
  return `${user.first_name} ${user.last_name}`.trim() || user.email;
}

/** The four office roles: the only ones the server lets coordinate. */
function isOfficeMember(user: UserListItem): boolean {
  return (STAFF_ROLES as readonly string[]).includes(user.role_name);
}

export default function UserListPage() {
  const addToast = useUIStore((s) => s.addToast);
  const viewer = useAuthStore((s) => s.user?.role_name);
  const viewerId = useAuthStore((s) => s.user?.id);
  const roleSelectId = useId();

  const [users, setUsers]     = useState<UserListItem[]>([]);
  const [total, setTotal]     = useState(0);
  const [page, setPage]       = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [search, setSearch]   = useState("");

  // Lock/unlock confirm dialog
  const [lockTarget, setLockTarget] = useState<UserListItem | null>(null);
  const [lockConfirming, setLockConfirming] = useState(false);
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
    setLockConfirming(true);
    try {
      await accountsApi.setLocked(lockTarget.id, !lockTarget.is_locked);
      addToast({ type: "success", message: `User ${lockTarget.is_locked ? "unlocked" : "locked"}.` });
      load(page);
    } catch {
      addToast({ type: "error", message: "Action failed." });
    } finally {
      setLockConfirming(false);
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

  const openCoordinator = useCallback((target: UserListItem) => {
    setCoordError(null);
    setCoordTarget(target);
  }, []);

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

  // Memoised on purpose: TanStack renders each `cell` function as a component,
  // so columns rebuilt every render would remount every row's menu, and a menu
  // that opens a dialog would lose the focus the dialog returns to (IR-1077).
  const columns = useMemo<ColumnDef<UserListItem, unknown>[]>(() => [
    {
      header: "User",
      id: "user",
      cell: ({ row }) => (
        <div className="min-w-0">
          <div className="font-medium text-stone-900">{displayName(row.original)}</div>
          <div className="text-[13px] text-stone-600">{row.original.email}</div>
        </div>
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
        <span className="inline-flex flex-wrap gap-1">
          <Badge variant={row.original.is_locked ? "danger" : row.original.is_active ? "success" : "neutral"}>
            {row.original.is_locked ? "Locked" : row.original.is_active ? "Active" : "Inactive"}
          </Badge>
          {/* Only the System Admin's list holds these; RDCO's leaves them out (IR-705, IR-804). */}
          {row.original.is_verified === false && <Badge variant="warning">Unverified</Badge>}
        </span>
      ),
    },
    {
      header: () => <span className="sr-only">Actions</span>,
      id: "actions",
      cell: ({ row }) => {
        const user = row.original;
        const items: RowMenuItem[] = rowActions(viewer, viewerId, user).map((action) => {
          switch (action) {
            case "change-role":
              return { key: action, label: "Change role", onSelect: () => { setRoleTarget(user); setNewRole(user.role_name); } };
            case "coordinator":
              return {
                key: action,
                label: user.is_office_coordinator ? "Remove coordinator" : "Make coordinator",
                onSelect: () => openCoordinator(user),
              };
            case "lock":
              return {
                key: action,
                label: user.is_locked ? "Unlock" : "Lock",
                danger: !user.is_locked,
                onSelect: () => setLockTarget(user),
              };
          }
        });
        return (
          <div className="flex justify-end">
            <RowMenu label={`Actions for ${displayName(user)}`} items={items} />
          </div>
        );
      },
    },
  ], [viewer, viewerId, openCoordinator]);

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
      <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
        <DataTable
          caption="User accounts"
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

      {/* Lock/unlock confirm: names the person, so a slip on the wrong row is seen. */}
      <ConfirmDialog
        open={!!lockTarget}
        title={`${lockTarget?.is_locked ? "Unlock" : "Lock"} ${lockTarget ? displayName(lockTarget) : ""}'s account?`}
        message={
          lockTarget
            ? lockTarget.is_locked
              ? `${displayName(lockTarget)} (${lockTarget.email}) will be able to log in again.`
              : `${displayName(lockTarget)} (${lockTarget.email}) will be prevented from logging in until the account is unlocked.`
            : ""
        }
        confirmLabel={lockTarget?.is_locked ? "Unlock" : "Lock"}
        danger={!lockTarget?.is_locked}
        confirming={lockConfirming}
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
          <p className="text-[14px] text-stone-600">
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
          <Select id={roleSelectId} label="New role" value={newRole} onChange={(e) => setNewRole(e.target.value)}>
            {rolesToOffer(viewer, roleTarget?.role_name ?? "").map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </Select>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setRoleTarget(null)}>Cancel</Button>
            <Button onClick={handleRoleChange}>Save</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
