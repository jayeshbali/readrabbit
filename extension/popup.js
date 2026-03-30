// Configuration - Update this to your API URL
const API_BASE = 'https://readrabbit.onrender.com/api';

// URLs that shouldn't be saved (not articles)
const BLOCKED_PATTERNS = [
  /^chrome:\/\//,
  /^chrome-extension:\/\//,
  /^about:/,
  /^file:\/\//,
  /google\.com\/search/,
  /bing\.com\/search/,
  /duckduckgo\.com/,
  /^https?:\/\/localhost/,
  /^https?:\/\/\d+\.\d+\.\d+\.\d+/,
];

// DOM elements
let urlDisplay, saveBtn, btnIcon, btnText, message, articleInfo;
let articleTitle, articleMeta, articleTopics, mainContent, notArticle;
let currentUrl = '';

document.addEventListener('DOMContentLoaded', async () => {
  // Get DOM elements
  urlDisplay = document.getElementById('url-display');
  saveBtn = document.getElementById('save-btn');
  btnIcon = document.getElementById('btn-icon');
  btnText = document.getElementById('btn-text');
  message = document.getElementById('message');
  articleInfo = document.getElementById('article-info');
  articleTitle = document.getElementById('article-title');
  articleMeta = document.getElementById('article-meta');
  articleTopics = document.getElementById('article-topics');
  mainContent = document.getElementById('main-content');
  notArticle = document.getElementById('not-article');
  
  // Get current tab URL
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    currentUrl = tab.url;
    
    // Check if it's a saveable URL
    if (isBlockedUrl(currentUrl)) {
      showNotArticle();
      return;
    }
    
    // Display truncated URL
    urlDisplay.textContent = truncateUrl(currentUrl, 50);
    urlDisplay.title = currentUrl;
    
  } catch (err) {
    urlDisplay.textContent = 'Unable to get page URL';
    saveBtn.disabled = true;
  }
  
  // Add click handler
  saveBtn.addEventListener('click', saveArticle);
});

function isBlockedUrl(url) {
  return BLOCKED_PATTERNS.some(pattern => pattern.test(url));
}

function truncateUrl(url, maxLength) {
  // Remove protocol
  let display = url.replace(/^https?:\/\//, '');
  // Remove www
  display = display.replace(/^www\./, '');
  
  if (display.length > maxLength) {
    return display.substring(0, maxLength) + '...';
  }
  return display;
}

function showNotArticle() {
  mainContent.style.display = 'none';
  notArticle.style.display = 'block';
}

function setButtonState(state) {
  switch (state) {
    case 'loading':
      saveBtn.disabled = true;
      saveBtn.className = 'save-btn';
      btnIcon.innerHTML = '<div class="spinner"></div>';
      btnText.textContent = 'Saving...';
      break;
    case 'success':
      saveBtn.disabled = true;
      saveBtn.className = 'save-btn success';
      btnIcon.textContent = '✓';
      btnText.textContent = 'Saved!';
      break;
    case 'error':
      saveBtn.disabled = false;
      saveBtn.className = 'save-btn error';
      btnIcon.textContent = '✕';
      btnText.textContent = 'Try Again';
      break;
    case 'default':
    default:
      saveBtn.disabled = false;
      saveBtn.className = 'save-btn';
      btnIcon.textContent = '📥';
      btnText.textContent = 'Save Article';
      break;
  }
}

function showMessage(text, type) {
  message.textContent = text;
  message.className = `message show ${type}`;
}

function showArticleInfo(article) {
  articleTitle.textContent = article.title || 'Untitled';
  
  const metaParts = [];
  if (article.source) metaParts.push(article.source);
  if (article.read_time) metaParts.push(`${article.read_time} min read`);
  articleMeta.textContent = metaParts.join(' · ');
  
  articleTopics.innerHTML = '';
  if (article.topics && article.topics.length > 0) {
    article.topics.slice(0, 4).forEach(topic => {
      const tag = document.createElement('span');
      tag.className = 'topic-tag';
      tag.textContent = topic;
      articleTopics.appendChild(tag);
    });
  }
  
  articleInfo.className = 'article-info show';
}

async function saveArticle() {
  if (!currentUrl) return;
  
  setButtonState('loading');
  message.className = 'message';
  articleInfo.className = 'article-info';
  
  try {
    const response = await fetch(`${API_BASE}/save-article`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url: currentUrl }),
    });
    
    const data = await response.json();
    
    if (!response.ok) {
      throw new Error(data.detail || 'Failed to save article');
    }
    
    setButtonState('success');
    showMessage('Article saved to your reading list!', 'success');
    
    if (data.article) {
      showArticleInfo(data.article);
    }
    
  } catch (err) {
    setButtonState('error');
    
    if (err.message.includes('already exists')) {
      showMessage('This article is already in your reading list.', 'error');
    } else {
      showMessage(err.message || 'Something went wrong. Please try again.', 'error');
    }
    
    // Reset button after 3 seconds
    setTimeout(() => {
      if (btnText.textContent === 'Try Again') {
        setButtonState('default');
      }
    }, 3000);
  }
}
