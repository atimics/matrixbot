import assert from 'node:assert/strict';
import test from 'node:test';
import { signupPath, signupReturnPath } from './signup-navigation.js';

test('signup and passkey pages retain the OIDC interaction', () => {
  const destination = '/interaction?interaction=oidc-session';
  const signup = new URL(signupPath('/signup', destination), 'https://id.rati.chat');
  const afterSignup = signupReturnPath(signup.searchParams.get('redirect'));
  const passkey = new URL(signupPath('/signup/add-passkey', afterSignup), signup);
  assert.equal(signupReturnPath(passkey.searchParams.get('redirect')), destination);
});

test('authorization parameters survive each signup step exactly', () => {
  const destination = '/authorize?state=a%2Bb&redirect_uri=https%3A%2F%2Fmatrix.rati.chat%2Fcallback&scope=openid';
  for (const step of ['/signup', '/signup/add-passkey', '/login']) {
    const next = new URL(signupPath(step, destination), 'https://id.rati.chat');
    assert.equal(signupReturnPath(next.searchParams.get('redirect')), destination);
  }
});

test('direct and invitation signups use the configured home page', () => {
  for (const destination of [null, undefined, '', '/settings']) {
    assert.equal(signupReturnPath(destination), '/settings');
    assert.equal(signupPath('/signup/add-passkey', destination), '/signup/add-passkey');
  }
});

test('untrusted return destinations use the configured home page', () => {
  for (const destination of [
    'https://example.com/interaction', '//example.com/interaction',
    'javascript:alert(1)', '/\\example.com/authorize', '/authorize\n',
    '/authorize\r', '/settings/admin/users', '/signup', '/interaction/evil',
    '/authorize#https://example.com', '/%2fexample.com/authorize',
    '/%5cexample.com/authorize', ' /authorize', '/authorize/../settings',
  ]) {
    assert.equal(signupReturnPath(destination), '/settings', destination);
  }
});
