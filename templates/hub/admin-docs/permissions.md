# Permissions

Repo or folder access is the operating boundary.

- `hub/`: admin only
- `hub/admin-docs/`: admin only
- `work-items/<id>/`: assigned collaborators and admins
- `knowledge-base/`: admin write by default; collaborators read unless delegated
- `local-private/`: local operator only; ignored by git

Connector access does not grant permission to change files, send external
messages, spend money, publish broadly, or alter access controls.
