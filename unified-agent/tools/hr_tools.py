#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HR Tools - Calculs RH (Congés, Jours ouvrables, etc.)
Intégration des outils HR de ChronoBrain
"""

import logging
from typing import Dict, Optional, Any
from datetime import datetime, timedelta, date

logger = logging.getLogger(__name__)


class HRTools:
    """Tools pour calculs RH"""
    
    @staticmethod
    def calculate_leave_balance(
        start_date: str,  # YYYY-MM-DD
        as_of: str,       # YYYY-MM-DD
        entitlement_per_year: float,
        taken_days: float = 0.0,
        carryover_days: float = 0.0,
        bonus_days: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Calcule le solde de congés
        
        Args:
            start_date: Date de début (YYYY-MM-DD)
            as_of: Date de calcul (YYYY-MM-DD)
            entitlement_per_year: Jours entitlement/an
            taken_days: Jours déjà pris
            carryover_days: Jours reportés
            bonus_days: Jours bonus spéciaux
            
        Returns:
            Dict avec solde détaillé
        """
        
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            as_of_date = datetime.strptime(as_of, "%Y-%m-%d").date()
            
            # Calcule jours accumulés
            days_employed = (as_of_date - start).days
            years_employed = days_employed / 365.25
            
            accrued_days = entitlement_per_year * years_employed
            
            # Total droits
            total_entitlement = accrued_days + carryover_days + bonus_days
            
            # Balance
            balance = total_entitlement - taken_days
            
            return {
                "start_date": start.isoformat(),
                "as_of": as_of_date.isoformat(),
                "entitlement_per_year": entitlement_per_year,
                "years_employed": round(years_employed, 2),
                "accrued_days": round(accrued_days, 2),
                "carryover_days": carryover_days,
                "bonus_days": bonus_days,
                "total_entitlement": round(total_entitlement, 2),
                "taken_days": taken_days,
                "balance_days": round(balance, 2),
                "warning": "Jours négatifs!" if balance < 0 else None,
            }
        
        except Exception as e:
            logger.error(f"Leave balance calculation error: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def working_days_between(
        start_date: str,  # YYYY-MM-DD
        end_date: str,    # YYYY-MM-DD
        country: str = "FR",
    ) -> Dict[str, Any]:
        """
        Calcule les jours ouvrables entre deux dates
        
        Args:
            start_date: Date de début (YYYY-MM-DD)
            end_date: Date de fin (YYYY-MM-DD)
            country: Code pays pour jours fériés (FR=France)
            
        Returns:
            Dict avec jours ouvrables
        """
        
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
            
            # Calcule jours calendaires
            calendar_days = (end - start).days + 1  # Inclusive
            
            # Compte les jours ouvrables (lun-ven)
            working_days = 0
            current = start
            
            while current <= end:
                # 0=lun, 6=dim
                if current.weekday() < 5:  # Lun-ven
                    working_days += 1
                
                current += timedelta(days=1)
            
            # Jours fériés français (simplifié, certaines dates fixes)
            holidays_fr = []
            if country == "FR":
                year = start.year
                holidays_fr = [
                    date(year, 1, 1),    # Jour de l'an
                    date(year, 5, 1),    # Fête du Travail
                    date(year, 5, 8),    # Victoire 1945
                    date(year, 7, 14),   # Bastille
                    date(year, 8, 15),   # Assomption
                    date(year, 11, 1),   # Toussaint
                    date(year, 11, 11),  # Armistice
                    date(year, 12, 25),  # Noël
                ]
            
            # Soustrait jours fériés tombant en semaine
            for holiday in holidays_fr:
                if start <= holiday <= end and holiday.weekday() < 5:
                    working_days -= 1
            
            return {
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "calendar_days": calendar_days,
                "working_days": working_days,
                "weekend_days": calendar_days - working_days,
                "country": country,
            }
        
        except Exception as e:
            logger.error(f"Working days calculation error: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def check_habilitation(
        role: str,
        required_level: int,
    ) -> Dict[str, Any]:
        """
        Check si un rôle a une habilitation
        
        Args:
            role: Rôle utilisateur
            required_level: Niveau requis (1=low, 3=high)
            
        Returns:
            Dict avec vérification
        """
        
        # Simplified role levels
        role_levels = {
            "junior": 1,
            "senior": 2,
            "manager": 2,
            "director": 3,
            "admin": 3,
        }
        
        user_level = role_levels.get(role.lower(), 0)
        
        return {
            "role": role,
            "user_level": user_level,
            "required_level": required_level,
            "has_habilitation": user_level >= required_level,
            "note": f"Rôle {role} {'a' if user_level >= required_level else 'n\'a pas'} l'habilitation"
        }


# Test simple
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test leave balance
    result = HRTools.calculate_leave_balance(
        start_date="2023-01-15",
        as_of="2024-01-15",
        entitlement_per_year=25,
        taken_days=5,
        carryover_days=3,
        bonus_days=2,
    )
    print("✓ Leave Balance:")
    for k, v in result.items():
        print(f"  {k}: {v}")
    
    # Test working days
    result = HRTools.working_days_between(
        start_date="2024-01-15",
        end_date="2024-01-22",
    )
    print("\n✓ Working Days:")
    for k, v in result.items():
        print(f"  {k}: {v}")
    
    # Test habilitation
    result = HRTools.check_habilitation(
        role="manager",
        required_level=2,
    )
    print("\n✓ Habilitation Check:")
    for k, v in result.items():
        print(f"  {k}: {v}")
