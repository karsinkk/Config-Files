# .bashrc

# Source global definitions
if [ -f /etc/bashrc ]; then
	. /etc/bashrc
fi

# Uncomment the following line if you don't like systemctl's auto-paging feature:
# export SYSTEMD_PAGER=

# User specific aliases and functions
export PROMPT_COMMAND='if [ "$(id -u)" -ne 0 ]; then echo "$(date "+%Y-%m-%d.%H:%M:%S") $(pwd) $(history 1)" >> ~/.logs/bash-history-$(date "+%Y-%m-%d").log; fi'
export JAVA_HOME=/usr/lib/jvm/java-1.8.0-openjdk-1.8.0.91-0.b14.el7_2.x86_64/jre/
export HADOOP_HOME=/home/karsinkk/BigData/hadoop/
export HADOOP_PREFIX=/home/karsinkk/BigData/hadoop/

export PATH="/home/karsinkk/anaconda3/bin:$PATH"
export PATH=$PATH:$HADOOP_HOME/bin:$JAVA_HOME:bin
