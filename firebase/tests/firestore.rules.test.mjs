import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} from '@firebase/rules-unit-testing';
import {
  collection,
  doc,
  getDoc,
  getDocs,
  orderBy,
  query,
  setDoc,
  where,
} from 'firebase/firestore';

const projectId = process.env.GCLOUD_PROJECT || 'demo-healthcare-f1';
let testEnv;

const userProfile = (uid, email) => ({
  id: uid,
  email,
  name: 'Test User',
  age: null,
  gender: null,
  equation_sex: null,
  nutrition_safety_profile: {},
  height: null,
  weight: null,
  targetWeight: null,
  activityLevel: null,
  healthGoal: null,
  createdAt: '2026-09-14T00:00:00.000Z',
});

before(async () => {
  testEnv = await initializeTestEnvironment({
    projectId,
    // firebase emulators:exec loads firebase/firestore.rules from firebase.json.
    // Do not upload the same rules a second time through the emulator admin
    // endpoint; that endpoint is not stable across all emulator releases.
    firestore: { host: '127.0.0.1', port: 8080 },
  });
  // Node 26 can negotiate the first local HTTP/2 stream unreliably even
  // though Firebase tooling officially supports Node 20/22/24. Warm the
  // transport outside rule assertions so a startup retry cannot masquerade as
  // an authorization result.
  await testEnv.withSecurityRulesDisabled(async (context) => {
    await setDoc(doc(context.firestore(), 'emulator_bootstrap/ready'), {
      ready: true,
    });
  });
});

after(async () => {
  await testEnv.cleanup();
});

test('unauthenticated access is denied', async () => {
  const db = testEnv.unauthenticatedContext().firestore();
  await assertFails(getDoc(doc(db, 'nguoi_dung/alice')));
});

test('a user can create and read a valid own profile', async () => {
  const db = testEnv
    .authenticatedContext('alice', { email: 'alice@example.test' })
    .firestore();
  const ref = doc(db, 'nguoi_dung/alice');
  await assertSucceeds(setDoc(ref, userProfile('alice', 'alice@example.test')));
  const snapshot = await assertSucceeds(getDoc(ref));
  assert.equal(snapshot.data().id, 'alice');
});

test('a user cannot read another private profile', async () => {
  await testEnv.withSecurityRulesDisabled(async (context) => {
    await setDoc(
      doc(context.firestore(), 'nguoi_dung/bob'),
      userProfile('bob', 'bob@example.test'),
    );
  });
  const alice = testEnv.authenticatedContext('alice').firestore();
  await assertFails(getDoc(doc(alice, 'nguoi_dung/bob')));
});

test('profile identity and shape cannot be forged', async () => {
  const alice = testEnv
    .authenticatedContext('alice', { email: 'alice@example.test' })
    .firestore();
  await assertFails(
    setDoc(
      doc(alice, 'nguoi_dung/alice'),
      userProfile('bob', 'alice@example.test'),
    ),
  );
  await assertFails(
    setDoc(doc(alice, 'nguoi_dung/alice'), {
      ...userProfile('alice', 'alice@example.test'),
      age: 5,
    }),
  );
});

test('owned body metrics can be created and queried', async () => {
  const alice = testEnv.authenticatedContext('alice').firestore();
  await assertSucceeds(
    setDoc(doc(alice, 'chi_so_co_the/metric-1'), {
      userId: 'alice',
      weight: 62.5,
      bmi: 22.1,
      recordedAt: '2026-09-14T00:00:00.000Z',
    }),
  );
  const ownQuery = query(
    collection(alice, 'chi_so_co_the'),
    where('userId', '==', 'alice'),
    orderBy('recordedAt', 'desc'),
  );
  const result = await assertSucceeds(getDocs(ownQuery));
  assert.equal(result.size, 1);
});

test('userId cannot be forged in a private log', async () => {
  const alice = testEnv.authenticatedContext('alice').firestore();
  await assertFails(
    setDoc(doc(alice, 'nhat_ky_an_uong/meal-1'), {
      id: 'meal-1',
      userId: 'bob',
      name: 'Phở',
      date: '2026-09-14T08:00:00.000Z',
      mealType: 'breakfast',
      items: [],
      isCompleted: true,
    }),
  );
});

test('all current owner-scoped log shapes accept valid writes', async () => {
  const alice = testEnv.authenticatedContext('alice').firestore();
  await assertSucceeds(
    setDoc(doc(alice, 'nhat_ky_an_uong/meal-1'), {
      id: 'meal-1',
      userId: 'alice',
      name: 'Phở',
      date: '2026-09-14T08:00:00.000Z',
      mealType: 'sang',
      items: [],
      isCompleted: true,
    }),
  );
  await assertSucceeds(
    setDoc(doc(alice, 'nhat_ky_tap_luyen/exercise-1'), {
      id: 'exercise-1',
      userId: 'alice',
      name: 'Đi bộ',
      exerciseTemplateId: null,
      date: '2026-09-14T09:00:00.000Z',
      duration: 30,
      caloriesBurned: 120.0,
      type: 'cardio',
      intensity: 'medium',
      isCompleted: true,
      timeOfDay: 'morning',
    }),
  );
  await assertSucceeds(
    setDoc(doc(alice, 'lifestyle_logs/alice_2026-09-14'), {
      id: 'alice_2026-09-14',
      userId: 'alice',
      date: '2026-09-14T00:00:00.000Z',
      moodScore: 4,
      sleepHours: 7.5,
      stressScore: 2,
      waterIntakeMl: 1000,
      notes: '',
    }),
  );
  await assertSucceeds(
    setDoc(doc(alice, 'lifestyle_reminders/reminder-1'), {
      id: 'reminder-1',
      userId: 'alice',
      title: 'Uống nước',
      type: 'water',
      time: '08:00',
      isActive: true,
      note: '',
    }),
  );
  await assertSucceeds(
    setDoc(doc(alice, 'water_intake/water-1'), {
      userId: 'alice',
      amount: 250,
      date: '2026-09-14T08:00:00.000Z',
    }),
  );
});

test('ownership cannot be transferred by update', async () => {
  await testEnv.withSecurityRulesDisabled(async (context) => {
    await setDoc(doc(context.firestore(), 'water_intake/water-1'), {
      userId: 'alice',
      amount: 250,
      date: '2026-09-14T08:00:00.000Z',
    });
  });
  const alice = testEnv.authenticatedContext('alice').firestore();
  await assertFails(
    setDoc(doc(alice, 'water_intake/water-1'), {
      userId: 'bob',
      amount: 250,
      date: '2026-09-14T08:00:00.000Z',
    }),
  );
});

test('canonical catalog writes are denied to normal clients', async () => {
  const alice = testEnv.authenticatedContext('alice').firestore();
  await assertFails(
    setDoc(doc(alice, 'mon_an/catalog-item-1'), {
      name: 'Không được ghi từ client',
    }),
  );
});

test('server/admin fixture path remains possible outside client rules', async () => {
  await assert.doesNotReject(async () => {
    await testEnv.withSecurityRulesDisabled(async (context) => {
      await setDoc(doc(context.firestore(), 'system_audit/server-1'), {
        status: 'fixture-only',
      });
    });
  });
});
