import React, { useState } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

const INPUT_TYPES = [
  { id: 'for-you', label: '✨ For You', placeholder: '' },
  { id: 'article', label: '📄 Article', placeholder: 'Paste article URL...' },
  { id: 'podcast', label: '🎙️ Podcast/Video', placeholder: 'Paste YouTube or podcast URL...' },
  { id: 'tweet', label: '🐦 Tweet', placeholder: 'Paste tweet/thread URL...' },
  { id: 'text', label: '💭 Describe', placeholder: 'Describe what you want to read about...' },
]

function DiscoverAgent({ onBack, onArticlesAdded }) {
  const [inputType, setInputType] = useState('for-you')
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [savingIds, setSavingIds] = useState(new Set())
  const [savedIds, setSavedIds] = useState(new Set())
  const [profile, setProfile] = useState(null)

  const handleDiscover = async () => {
    if (inputType !== 'for-you' && !content.trim()) return
    
    setLoading(true)
    setError(null)
    setResult(null)
    setSavedIds(new Set())
    setProfile(null)
    
    try {
      let res;
      
      if (inputType === 'for-you') {
        // For You mode - analyze entire library
        res = await fetch(`${API_BASE}/agent/for-you`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ max_results: 5 }),
        })
      } else {
        // Regular discovery mode
        res = await fetch(`${API_BASE}/agent/discover`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            content: content.trim(),
            input_type: inputType,
            max_results: 5,
            auto_save: false,
          }),
        })
      }
      
      const data = await res.json()
      
      if (!res.ok) {
        throw new Error(data.detail || 'Discovery failed')
      }
      
      if (data.profile) {
        setProfile(data.profile)
      }
      
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async (rec) => {
    setSavingIds(prev => new Set([...prev, rec.url]))
    
    try {
      const res = await fetch(`${API_BASE}/agent/save-recommendation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(rec),
      })
      
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Failed to save')
      }
      
      setSavedIds(prev => new Set([...prev, rec.url]))
      if (onArticlesAdded) onArticlesAdded()
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingIds(prev => {
        const next = new Set(prev)
        next.delete(rec.url)
        return next
      })
    }
  }

  const handleSaveAll = async () => {
    if (!result?.recommendations) return
    
    const unsaved = result.recommendations.filter(r => !savedIds.has(r.url))
    for (const rec of unsaved) {
      await handleSave(rec)
    }
  }

  const currentInput = INPUT_TYPES.find(t => t.id === inputType)

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-3 sm:px-4 py-3 sm:py-4">
          <div className="flex items-center gap-2 sm:gap-3">
            <button
              onClick={onBack}
              className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <div>
              <h1 className="text-lg sm:text-xl font-bold text-gray-900">🔍 Discovery</h1>
              <p className="text-xs sm:text-sm text-gray-500 hidden sm:block">Find similar articles based on content you like</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-3 sm:px-4 py-4 sm:py-8">
        {/* Input Section */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 sm:p-6 mb-4 sm:mb-6">
          <h2 className="text-base sm:text-lg font-semibold text-gray-900 mb-3 sm:mb-4">What inspires you?</h2>
          
          {/* Input Type Toggle - scrollable on mobile */}
          <div className="flex gap-2 mb-4 overflow-x-auto pb-2 -mx-1 px-1 scrollbar-hide">
            {INPUT_TYPES.map(type => (
              <button
                key={type.id}
                onClick={() => setInputType(type.id)}
                className={`px-3 sm:px-4 py-1.5 sm:py-2 rounded-lg text-xs sm:text-sm font-medium transition-colors whitespace-nowrap flex-shrink-0 ${
                  inputType === type.id
                    ? type.id === 'for-you' 
                      ? 'bg-purple-100 text-purple-700 border border-purple-200'
                      : 'bg-orange-100 text-orange-700 border border-orange-200'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200 border border-transparent'
                }`}
              >
                {type.label}
              </button>
            ))}
          </div>

          {/* For You Mode */}
          {inputType === 'for-you' ? (
            <div className="bg-purple-50 border border-purple-100 rounded-lg p-3 sm:p-4 mb-4">
              <p className="text-purple-800 text-xs sm:text-sm">
                <strong>✨ For You</strong> analyzes your library to find articles you'll love.
              </p>
            </div>
          ) : (
            <>
              {/* Input Field */}
              {inputType === 'text' ? (
                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder={currentInput.placeholder}
                  rows={3}
                  className="w-full px-3 sm:px-4 py-2.5 sm:py-3 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent resize-none text-sm sm:text-base"
                />
              ) : (
                <input
                  type="url"
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder={currentInput.placeholder}
                  className="w-full px-3 sm:px-4 py-2.5 sm:py-3 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent text-sm sm:text-base"
                  onKeyDown={(e) => e.key === 'Enter' && handleDiscover()}
                />
              )}
              
              {/* Hint for podcast/video */}
              {inputType === 'podcast' && (
                <p className="text-xs text-gray-400 mt-2">
                  ✨ YouTube URLs will extract transcript for better results
                </p>
              )}
            </>
          )}

          {/* Discover Button */}
          <div className="flex justify-end mt-4">
            <button
              onClick={handleDiscover}
              disabled={loading || (inputType !== 'for-you' && !content.trim())}
              className={`w-full sm:w-auto px-5 sm:px-6 py-2.5 sm:py-3 text-white font-medium rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2 text-sm sm:text-base ${
                inputType === 'for-you' 
                  ? 'bg-purple-500 hover:bg-purple-600' 
                  : 'bg-orange-500 hover:bg-orange-600'
              }`}
            >
              {loading ? (
                <>
                  <svg className="animate-spin h-4 w-4 sm:h-5 sm:w-5" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>{inputType === 'for-you' ? 'Analyzing...' : 'Discovering...'}</span>
                </>
              ) : (
                <>
                  <span>{inputType === 'for-you' ? '✨' : '🔍'}</span>
                  <span>{inputType === 'for-you' ? 'Find For Me' : 'Find Articles'}</span>
                </>
              )}
            </button>
          </div>

          {/* Error */}
          {error && (
            <div className="mt-4 p-3 bg-red-50 text-red-700 rounded-lg">
              {error}
            </div>
          )}
        </div>

        {/* Loading State */}
        {loading && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-8 text-center">
            <div className="animate-pulse">
              <div className="text-4xl mb-4">🐰</div>
              <p className="text-gray-600">
                {inputType === 'for-you' 
                  ? 'Analyzing your reading profile...' 
                  : 'Agent is searching for great reads...'}
              </p>
              <p className="text-sm text-gray-400 mt-2">This may take 15-30 seconds</p>
            </div>
          </div>
        )}

        {/* Reading Profile (For You mode) */}
        {profile && !loading && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
            <h3 className="font-semibold text-gray-900 mb-4">📊 Your Reading Profile</h3>
            
            {/* Interest Breakdown */}
            {profile.interest_breakdown && (
              <div className="mb-4">
                <p className="text-sm text-gray-500 mb-2">Interest Areas</p>
                <div className="space-y-2">
                  {profile.interest_breakdown.map(item => (
                    <div key={item.topic} className="flex items-center gap-3">
                      <div className="flex-1">
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-gray-700">{item.topic}</span>
                          <span className="text-gray-500">{item.percentage}%</span>
                        </div>
                        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-purple-500 rounded-full" 
                            style={{ width: `${item.percentage}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {/* Favorite Sources */}
            {profile.favorite_sources?.length > 0 && (
              <div className="mb-4">
                <p className="text-sm text-gray-500 mb-2">Favorite Sources</p>
                <div className="flex flex-wrap gap-2">
                  {profile.favorite_sources.map(source => (
                    <span key={source} className="px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-sm">
                      {source}
                    </span>
                  ))}
                </div>
              </div>
            )}
            
            {/* Profile Summary */}
            {profile.profile_summary && (
              <p className="text-sm text-gray-600 italic">
                "{profile.profile_summary}"
              </p>
            )}
          </div>
        )}

        {/* Results */}
        {result && !loading && (
          <div className="space-y-4 sm:space-y-6">
            {/* Themes Found (non-For You mode) */}
            {result.themes && !profile && (
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 sm:p-6">
                <h3 className="font-semibold text-gray-900 mb-2 sm:mb-3 text-sm sm:text-base">🎯 Themes Identified</h3>
                <div className="flex flex-wrap gap-1.5 sm:gap-2">
                  {result.themes?.main_topics?.map(topic => (
                    <span key={topic} className="px-2 sm:px-3 py-0.5 sm:py-1 bg-orange-100 text-orange-700 rounded-full text-xs sm:text-sm">
                      {topic}
                    </span>
                  ))}
                  {result.themes?.key_concepts?.map(concept => (
                    <span key={concept} className="px-2 sm:px-3 py-0.5 sm:py-1 bg-blue-100 text-blue-700 rounded-full text-xs sm:text-sm">
                      {concept}
                    </span>
                  ))}
                </div>
                <p className="text-xs sm:text-sm text-gray-500 mt-2 sm:mt-3">
                  Searched {result.searches_performed} queries • Evaluated {result.results_evaluated} results
                </p>
              </div>
            )}

            {/* Recommendations */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 sm:p-6">
              <div className="flex items-center justify-between mb-3 sm:mb-4">
                <h3 className="font-semibold text-gray-900 text-sm sm:text-base">
                  📚 Recommendations ({result.recommendations?.length || 0})
                </h3>
                {result.recommendations?.length > 0 && (
                  <button
                    onClick={handleSaveAll}
                    disabled={savedIds.size === result.recommendations.length}
                    className="text-xs sm:text-sm px-3 sm:px-4 py-1.5 sm:py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50"
                  >
                    Save All
                  </button>
                )}
              </div>

              {result.recommendations?.length === 0 ? (
                <p className="text-gray-500 text-center py-6 sm:py-8 text-sm">
                  No new recommendations found. Try different input!
                </p>
              ) : (
                <div className="space-y-3 sm:space-y-4">
                  {result.recommendations?.map((rec, idx) => (
                    <div key={rec.url} className="border border-gray-100 rounded-lg p-3 sm:p-4 hover:border-gray-200 transition-colors">
                      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-3">
                        <div className="flex-1 min-w-0">
                          <a
                            href={rec.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-medium text-gray-900 hover:text-orange-600 line-clamp-2 sm:line-clamp-1 text-sm sm:text-base"
                          >
                            {rec.title}
                          </a>
                          
                          <div className="flex flex-wrap items-center gap-1 sm:gap-2 text-xs sm:text-sm text-gray-500 mt-1">
                            {rec.source && <span className="truncate max-w-[120px]">{rec.source}</span>}
                            {rec.read_time && (
                              <>
                                <span>·</span>
                                <span>{rec.read_time}m</span>
                              </>
                            )}
                            {rec.quality_score && (
                              <>
                                <span>·</span>
                                <span className="text-orange-600">{rec.quality_score}/10</span>
                              </>
                            )}
                          </div>

                          {rec.summary && (
                            <p className="text-xs sm:text-sm text-gray-600 mt-2 line-clamp-2 hidden sm:block">
                              {rec.summary}
                            </p>
                          )}

                          {rec.topics?.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-2">
                              {rec.topics.slice(0, 3).map(topic => (
                                <span key={topic} className="px-1.5 sm:px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">
                                  {topic}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>

                        <button
                          onClick={() => handleSave(rec)}
                          disabled={savingIds.has(rec.url) || savedIds.has(rec.url)}
                          className={`w-full sm:w-auto flex-shrink-0 px-3 sm:px-4 py-2 rounded-lg font-medium text-xs sm:text-sm transition-colors ${
                            savedIds.has(rec.url)
                              ? 'bg-green-100 text-green-700'
                              : savingIds.has(rec.url)
                              ? 'bg-gray-100 text-gray-500'
                              : 'bg-orange-500 text-white hover:bg-orange-600'
                          }`}
                        >
                          {savedIds.has(rec.url) ? '✓ Saved' : savingIds.has(rec.url) ? 'Saving...' : 'Save'}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* How It Works */}
        {!result && !loading && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 sm:p-6">
            <h3 className="font-semibold text-gray-900 mb-3 sm:mb-4 text-sm sm:text-base">How it works</h3>
            {inputType === 'for-you' ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-4 text-xs sm:text-sm">
                <div className="text-center p-2 sm:p-4">
                  <div className="text-xl sm:text-2xl mb-1 sm:mb-2">1️⃣</div>
                  <p className="text-gray-600">Analyzes library</p>
                </div>
                <div className="text-center p-2 sm:p-4">
                  <div className="text-xl sm:text-2xl mb-1 sm:mb-2">2️⃣</div>
                  <p className="text-gray-600">Builds profile</p>
                </div>
                <div className="text-center p-2 sm:p-4">
                  <div className="text-xl sm:text-2xl mb-1 sm:mb-2">3️⃣</div>
                  <p className="text-gray-600">Searches content</p>
                </div>
                <div className="text-center p-2 sm:p-4">
                  <div className="text-xl sm:text-2xl mb-1 sm:mb-2">4️⃣</div>
                  <p className="text-gray-600">Recommends articles</p>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-4 text-xs sm:text-sm">
                <div className="text-center p-2 sm:p-4">
                  <div className="text-xl sm:text-2xl mb-1 sm:mb-2">1️⃣</div>
                  <p className="text-gray-600">Paste URL or describe</p>
                </div>
                <div className="text-center p-2 sm:p-4">
                  <div className="text-xl sm:text-2xl mb-1 sm:mb-2">2️⃣</div>
                  <p className="text-gray-600">AI extracts themes</p>
                </div>
                <div className="text-center p-2 sm:p-4">
                  <div className="text-xl sm:text-2xl mb-1 sm:mb-2">3️⃣</div>
                  <p className="text-gray-600">Searches similar</p>
                </div>
                <div className="text-center p-2 sm:p-4">
                  <div className="text-xl sm:text-2xl mb-1 sm:mb-2">4️⃣</div>
                  <p className="text-gray-600">Save favorites</p>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}

export default DiscoverAgent
