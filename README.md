要預覽您剛才建立的網站，您需要在本機上同時執行後端伺服器和前端應用程式。以下是詳細步驟：

1. 啟動後端伺服器

首先，請打開一個新的終端機視窗。
進入後端目錄：cd backend
安裝所有必要的 Python 套件：pip install -r requirements.txt
啟動 Flask 伺服器：python app.py
您會看到伺服器在 http://127.0.0.1:5001 上運行的訊息。請讓這個終端機視窗保持開啟。
2. 啟動前端應用程式

現在，請再打開另一個新的終端機視窗。
進入前端目錄：cd frontend
安裝所有必要的 JavaScript 套件：npm install
啟動 React 開發伺服器：npm start
3. 預覽網站

執行 npm start 後，您的預設瀏覽器應該會自動開啟一個指向 http://localhost:3000 的新分頁。
如果沒有自動開啟，您可以手動在瀏覽器中輸入 http://localhost:3000。
這時，您應該就能看到並與您設計的 AI 股價分析工具互動了。請讓兩個終端機視窗都保持運行，以便前後端可以互相通訊。
