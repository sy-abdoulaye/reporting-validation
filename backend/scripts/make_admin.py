#!/usr/bin/env python
"""Promeut (ou rétrograde) un utilisateur en administrateur.

Exemples :
    python scripts/make_admin.py monadmin
    python scripts/make_admin.py user@example.com
    python scripts/make_admin.py monadmin --revoke   # retire les droits admin
    python scripts/make_admin.py --list              # liste les comptes

En Docker :
    docker exec reporting-backend python scripts/make_admin.py <identifiant>
"""

import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.user import User


def _find_user(db, identifier):
    return (
        db.query(User)
        .filter((User.username == identifier) | (User.email == identifier))
        .first()
    )


def main():
    parser = argparse.ArgumentParser(description="Gestion des droits administrateur")
    parser.add_argument("identifier", nargs="?", help="Nom d'utilisateur ou email")
    parser.add_argument("--revoke", action="store_true", help="Retirer les droits admin")
    parser.add_argument("--list", action="store_true", help="Lister les utilisateurs")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.list:
            users = db.query(User).order_by(User.created_at).all()
            if not users:
                print("Aucun utilisateur.")
                return
            for u in users:
                role = "ADMIN" if u.is_superuser else "user "
                state = "actif" if u.is_active else "inactif"
                print(f"  [{role}] {u.username:<20} {u.email:<35} ({state})")
            return

        if not args.identifier:
            parser.error("fournissez un nom d'utilisateur/email, ou utilisez --list")

        user = _find_user(db, args.identifier)
        if not user:
            print(f"❌ Utilisateur introuvable : {args.identifier}")
            sys.exit(1)

        user.is_superuser = not args.revoke
        db.commit()

        if args.revoke:
            print(f"✅ Droits admin retirés à « {user.username} » ({user.email}).")
        else:
            print(f"✅ « {user.username} » ({user.email}) est désormais administrateur.")
        print("ℹ️  L'utilisateur doit se reconnecter pour rafraîchir son token.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
