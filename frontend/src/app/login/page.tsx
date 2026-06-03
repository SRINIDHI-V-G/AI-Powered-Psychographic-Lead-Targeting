'use client';

import { useState } from 'react';
import { Lightbulb, Eye, EyeOff, Loader2 } from 'lucide-react';
import { useAuth } from '@/lib/hooks/useAuth';

export default function LoginPage() {
  const { login, loginDemo, loading, error } = useAuth();
  const [key, setKey] = useState('');
  const [show, setShow] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    await login(key);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-950 via-indigo-900 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex w-14 h-14 bg-indigo-500 rounded-2xl items-center justify-center mb-4">
            <Lightbulb size={28} className="text-white" />
          </div>
          <h1 className="text-3xl font-bold text-white">PsychoLead AI</h1>
          <p className="text-indigo-300 mt-2 text-sm">
            AI-powered psychographic lead targeting
          </p>
        </div>

        <div className="bg-white rounded-2xl shadow-xl p-8">
          <h2 className="text-xl font-semibold text-slate-800 mb-1">Connect your account</h2>
          <p className="text-sm text-slate-500 mb-6">Enter your API key to get started</p>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label htmlFor="apikey" className="block text-sm font-medium text-slate-700 mb-1.5">
                API Key
              </label>
              <div className="relative">
                <input
                  id="apikey"
                  type={show ? 'text' : 'password'}
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                  placeholder="pl_xxxxxxxxxxxxxxxx"
                  autoComplete="current-password"
                  className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShow(!show)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition"
                >
                  {show ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 transition disabled:opacity-60 flex items-center justify-center gap-2"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : null}
              Connect
            </button>
          </form>

          <div className="relative my-5">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-slate-200" />
            </div>
            <div className="relative flex justify-center">
              <span className="bg-white px-3 text-xs text-slate-400">or</span>
            </div>
          </div>

          <button
            type="button"
            onClick={loginDemo}
            disabled={loading}
            className="w-full py-2.5 border-2 border-indigo-200 text-indigo-700 font-semibold rounded-xl hover:bg-indigo-50 transition disabled:opacity-60 flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : null}
            Try Demo Mode
          </button>
          <p className="text-xs text-slate-400 text-center mt-2">
            Loads sample data instantly — no account needed
          </p>
        </div>
      </div>
    </div>
  );
}
