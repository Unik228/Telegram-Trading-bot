# 🤖 CryptoSentinel AI Trader

**CryptoSentinel AI Trader** est un bot de trading automatisé multi-exchange (Bybit, OKX, Kraken) conçu pour surveiller et exécuter des arbitrages ou ordres de marché de manière intelligente et sécurisée.

---

## 🚀 Fonctionnalités

- Connexion sécurisée aux APIs de :
  - ✅ Bybit
  - ✅ OKX
  - ✅ Kraken
- 🔁 Trading sur toutes les paires disponibles
- 💹 Détection automatique d'opportunités rentables
- 📊 Rapport de performance journalier (profits, ROI, nombre de trades)
- 🧠 Filtres de spread (arbitrage intelligent)
- 🛠️ Commandes Telegram intégrées :
  - `/start` : Lancer le bot
  - `/stop` : Arrêter le bot
  - `/status` : Statut actuel
  - `/balance` : Afficher le solde total

---

## 🔐 Configuration `.env`

Crée un fichier `.env` (non versionné) dans la racine du projet :

```env
# Telegram
TELEGRAM_BOT_TOKEN=xxxxxxxxxx
TELEGRAM_CHAT_ID=xxxxxxxxxx

# BYBIT
BYBIT_API_KEY=xxxxxxxxxx
BYBIT_API_SECRET=xxxxxxxxxx

# OKX
OKX_API_KEY=xxxxxxxxxx
OKX_API_SECRET=xxxxxxxxxx
OKX_API_PASSPHRASE=xxxxxxxxxx

# KRAKEN
KRAKEN_API_KEY=xxxxxxxxxx
KRAKEN_API_SECRET=xxxxxxxxxx
