# 🤖 Telegram Crypto Trading Bot

Un bot automatisé de trading pour les plateformes **Binance** et **Bybit**, qui envoie des signaux sur Telegram et peut passer des ordres réels de manière sécurisée.

## 🚀 Fonctionnalités

- ✅ Analyse automatique de la rentabilité toutes les 30 minutes
- 📈 Passage d’ordres d’achat/vente avec :
  - Objectif de **+2% de profit**
  - Gestion des **stop-loss**
  - **Taille d’ordre fixe** (10 USDT par trade)
- 🔒 Vérification du solde avant chaque trade
- 📤 Envoi des signaux dans un canal ou groupe Telegram
- 📓 Système de **journalisation** des ordres exécutés

## 🔧 Technologies utilisées

- `python-binance` pour l'intégration Binance
- `bybit` SDK officiel pour l'API de Bybit
- `python-telegram-bot` pour l’envoi automatique des signaux
- `.env` pour la sécurité des clés API

---

## 🧰 Installation

1. Clone le projet :
```bash
git clone https://github.com/TON_UTILISATEUR/Telegram-Trading-Bot.git
cd Telegram-Trading-Bot

