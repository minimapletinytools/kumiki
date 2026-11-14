// Gives shell.js (a classic script) the key matcher the panels' modules use: window.kigumiKeyFromEvent.
import { keyFromEvent } from '../key-match.js';

window.kigumiKeyFromEvent = keyFromEvent;
