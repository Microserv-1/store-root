import jenkins.model.Jenkins
import hudson.security.HudsonPrivateSecurityRealm
import hudson.security.FullControlOnceLoggedInAuthorizationStrategy
import com.cloudbees.plugins.credentials.SystemCredentialsProvider
import com.cloudbees.plugins.credentials.CredentialsScope
import com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl

def instance = Jenkins.get()
def password = System.getenv('JENKINS_ADMIN_PASSWORD')
if (!password || password.length() < 32) throw new IllegalStateException('Random local admin password required')
def realm = new HudsonPrivateSecurityRealm(false)
realm.createAccount('admin', password)
instance.setSecurityRealm(realm)
def strategy = new FullControlOnceLoggedInAuthorizationStrategy()
strategy.setAllowAnonymousRead(false)
instance.setAuthorizationStrategy(strategy)
instance.setNumExecutors(1)
instance.setLabelString('docker-kubectl')
instance.setSlaveAgentPort(-1)
def credentials = SystemCredentialsProvider.getInstance()
if (System.getenv('STORE_JENKINS_CONTAINER_NETWORK') == 'true' && !credentials.credentials.any { it.id == 'github-read' }) {
    credentials.credentials.add(new UsernamePasswordCredentialsImpl(CredentialsScope.GLOBAL,
        'github-read', 'Local SCM mirrors only; no GitHub token', 'local-scm', 'unused-local-scm'))
    credentials.save()
}
instance.save()
